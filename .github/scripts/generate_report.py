#!/usr/bin/env python3

import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import requests
from pathlib import Path
import math

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
ORG_NAME = os.environ.get('ORG_NAME')
# Adjusted REPOS to reflect the Social Network project structure more accurately
# Assuming 'frontend', 'backend', 'mobile', 'devops' are your primary repos
REPOS = ['frontend', 'backend', 'mobile', 'devops', 'testing']
WEEK_NUMBER = os.environ.get('WEEK_NUMBER')
YEAR = os.environ.get('YEAR')

if not GITHUB_TOKEN or not ORG_NAME:
    print("Error: GITHUB_TOKEN and ORG_NAME environment variables must be set")
    sys.exit(1)

HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# --- Utility Functions ---

def get_week_range():
    """Get start and end dates for the specified or current week."""
    if WEEK_NUMBER and YEAR:
        try:
            week_num = int(WEEK_NUMBER)
            year = int(YEAR)
            
            # Calculate the first day of the year
            jan_1 = datetime(year, 1, 1, tzinfo=timezone.utc)
            # Find the first Monday of the year (ISO week 1 starts on Monday)
            # ISO week 1 is the first week with at least 4 days in the new year.
            # day_of_week 0=Monday, 6=Sunday
            
            # Determine the weekday of Jan 1st
            jan_1_weekday = jan_1.weekday()
            
            # Calculate days to reach the first Monday of ISO week 1
            # If Jan 1 is Mon, Tue, Wed, Thu, it's in week 1.
            # If Jan 1 is Fri, Sat, Sun, it's in the last week of the previous year,
            # so we need to go to the next Monday.
            
            if jan_1_weekday <= 3: # Jan 1 is Mon, Tue, Wed, Thu
                first_monday_of_year = jan_1 - timedelta(days=jan_1_weekday)
            else: # Jan 1 is Fri, Sat, Sun
                first_monday_of_year = jan_1 + timedelta(days=(7 - jan_1_weekday))
            
            start_of_week = first_monday_of_year + timedelta(weeks=week_num - 1)
            end_of_week = start_of_week + timedelta(days=7) # Exclusive end date
            
            print(f"Using manually specified week: Week {week_num}, {year}")
        except ValueError:
            print("Invalid WEEK_NUMBER or YEAR. Falling back to current week.")
            return get_current_week_range()
    else:
        print("WEEK_NUMBER or YEAR not set. Falling back to current week.")
        return get_current_week_range()
    
    return start_of_week, end_of_week

def get_current_week_range():
    """Get start and end dates for the current ISO week."""
    now = datetime.now(timezone.utc)
    # Calculate the start of the current ISO week (Monday)
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=7)
    
    week_num = now.isocalendar()[1]
    year = now.year
    print(f"Using current ISO week: Week {week_num}, {year}")
    
    return start_of_week, end_of_week


def format_date(date):
    """Format date as YYYY-MM-DD."""
    return date.strftime('%Y-%m-%d')

def format_datetime(dt_str):
    """Format datetime string."""
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return dt.strftime('%Y-%m-%d %H:%M UTC')

def capitalize_repo_name(repo_name):
    """Properly capitalize repository names, removing prefixes."""
    if repo_name.startswith('social-network-'):
        return repo_name.replace('social-network-', '').replace('-', ' ').title()
    return repo_name.replace('-', ' ').title()

def github_api_get(url, params=None):
    """Make GET request to GitHub API."""
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error for {url}: {e}")
        return [] if "list" in url else {}

def fetch_repo_activity(repo, start, end):
    """Fetch all activity for a repository in the date range."""
    print(f"  Fetching activity for {repo}...")
    
    commits_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/commits'
    commits_params = {'since': start.isoformat(), 'until': end.isoformat(), 'per_page': 100}
    commits = github_api_get(commits_url, commits_params)
    if not isinstance(commits, list):
        commits = []
    
    issues_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues'
    # Fetch issues that were created, updated, or closed within the range
    # GitHub API `since` parameter applies to `updated_at`
    issues_params = {'state': 'all', 'since': start.isoformat(), 'per_page': 100} 
    all_issues = github_api_get(issues_url, issues_params)
    if not isinstance(all_issues, list):
        all_issues = []
    
    # Filter issues to only include those truly active in the period
    issues = []
    for item in all_issues:
        created_at_dt = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
        updated_at_dt = datetime.fromisoformat(item['updated_at'].replace('Z', '+00:00'))
        closed_at_dt = datetime.fromisoformat(item['closed_at'].replace('Z', '+00:00')) if item.get('closed_at') else None
        
        # An item is relevant if it was created, updated, or closed within the reporting period
        if (start <= created_at_dt < end) or \
           (start <= updated_at_dt < end) or \
           (closed_at_dt and start <= closed_at_dt < end):
            issues.append(item)

    prs_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls'
    # Fetch PRs that were created, updated, or merged/closed within the range
    prs_params = {'state': 'all', 'sort': 'updated', 'direction': 'desc', 'since': start.isoformat(), 'per_page': 100}
    all_prs = github_api_get(prs_url, prs_params)
    if not isinstance(all_prs, list):
        all_prs = []
    
    # Filter PRs for activity within the reporting period
    prs = []
    for pr in all_prs:
        created_at_dt = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
        updated_at_dt = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
        merged_at_dt = datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) if pr.get('merged_at') else None
        closed_at_dt = datetime.fromisoformat(pr['closed_at'].replace('Z', '+00:00')) if pr.get('closed_at') and not pr.get('merged_at') else None # Only closed if not merged
        
        if (start <= created_at_dt < end) or \
           (start <= updated_at_dt < end) or \
           (merged_at_dt and start <= merged_at_dt < end) or \
           (closed_at_dt and start <= closed_at_dt < end):
            prs.append(pr)
    
    print(f"    Found: {len(commits)} commits, {len(issues)} issues, {len(prs)} PRs")
    
    return {
        'commits': commits,
        'issues': issues,
        'pull_requests': prs
    }

def get_issue_type(issue):
    """Determine issue type from labels."""
    labels = [label['name'].lower() for label in issue.get('labels', [])]
    
    type_keywords = {
        'Bug': ['bug', 'fix', 'error', 'defect'],
        'Feature': ['feature', 'enhancement', 'new'],
        'Documentation': ['docs', 'documentation'],
        'Task': ['task', 'chore'],
        'Security': ['security', 'vulnerability'],
        'Performance': ['performance', 'optimization', 'perf']
    }
    
    for issue_type, keywords in type_keywords.items():
        if any(keyword in label for label in labels for keyword in keywords):
            return issue_type
    
    return 'Task'

def get_priority(issue):
    """Extract priority from labels."""
    labels = [label['name'].lower() for label in issue.get('labels', [])]
    
    for label in labels:
        if 'critical' in label or 'p0' in label:
            return 'Critical'
        if 'high' in label or 'p1' in label:
            return 'High'
        if 'medium' in label or 'p2' in label:
            return 'Medium'
        if 'low' in label or 'p3' in label:
            return 'Low'
    
    return 'Unset'

def calculate_time_to_close(issue):
    """Calculate time from creation to closure."""
    if not issue.get('closed_at'):
        return None
    
    created = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
    closed = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
    delta = closed - created
    
    return delta

def format_timedelta(delta):
    """Format timedelta as readable string."""
    if delta is None:
        return 'N/A'
    
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

# --- PDF Generation Function ---

def generate_pdf_report(all_data, week_range):
    """Generate a concise, professional PDF report."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus.flowables import KeepTogether
    
    start, end = week_range
    week_num = end.isocalendar()[1]
    year = end.year
    
    # Create PDF
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    filename = f"weekly_progress_report_W{week_num}_Y{year}.pdf"
    filepath = reports_dir / filename
    
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Professional, subdued color scheme (darker grays, subtle accent)
    PRIMARY_COLOR = colors.HexColor('#212121') # Dark Gray
    SECONDARY_COLOR = colors.HexColor('#424242') # Medium Dark Gray
    ACCENT_COLOR = colors.HexColor('#607D8B') # Blue Grey
    HEADER_BG = colors.HexColor('#E0E0E0') # Light Gray
    TABLE_HEADER_COLOR_1 = colors.HexColor('#757575') # Gray 700
    TABLE_HEADER_COLOR_2 = colors.HexColor('#616161') # Gray 800
    
    # Custom styles - more compact and formal
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20, # Reduced
        textColor=PRIMARY_COLOR,
        spaceAfter=0.2*cm, # Reduced
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=24 # Reduced
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11, # Reduced
        textColor=SECONDARY_COLOR,
        spaceAfter=0.1*cm, # Reduced
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    meta_style = ParagraphStyle(
        'MetaInfo',
        parent=styles['Normal'],
        fontSize=8, # Reduced
        textColor=colors.HexColor('#757575'),
        spaceAfter=0.5*cm, # Reduced
        alignment=TA_CENTER
    )
    
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=16, # Reduced
        textColor=PRIMARY_COLOR,
        spaceAfter=0.5*cm, # Reduced
        spaceBefore=1.0*cm, # Reduced
        fontName='Helvetica-Bold',
        leftIndent=0
    )
    
    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=12, # Reduced
        textColor=SECONDARY_COLOR,
        spaceAfter=0.3*cm, # Reduced
        spaceBefore=0.8*cm, # Reduced
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=9, # Reduced
        textColor=colors.HexColor('#212121'),
        alignment=TA_JUSTIFY,
        spaceAfter=0.2*cm, # Reduced
        leading=11 # Reduced
    )

    table_cell_style_small = ParagraphStyle(
        'TableCellSmall',
        parent=styles['Normal'],
        fontSize=7, # Very small for detail
        leading=8,
        alignment=TA_LEFT,
        textColor=PRIMARY_COLOR,
    )
    
    # --- Title Page ---
    elements.append(Spacer(1, 2*cm))
    elements.append(Paragraph("SOCIAL NETWORK PROJECT", title_style))
    elements.append(Paragraph("WEEKLY PROGRESS REPORT", title_style))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"Week {week_num}, {year}", subtitle_style))
    elements.append(Spacer(1, 0.5*cm))
    
    elements.append(HRFlowable(width="80%", thickness=1, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))
    
    elements.append(Paragraph(f"<b>Organization:</b> {ORG_NAME}", subtitle_style))
    elements.append(Paragraph(f"<b>Reporting Period:</b> {format_date(start)} to {format_date(end - timedelta(days=1))}", subtitle_style)) # Adjust end date for display
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", meta_style))
    
    elements.append(PageBreak())
    
    # --- Executive Summary ---
    
    # Calculate comprehensive totals
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_issues_created = sum(len([i for i in repo['issues'] if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_opened = sum(len([pr for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    
    # Ensure to get additions/deletions only for PRs opened within the reporting period for summary
    total_lines_added = sum(pr.get('additions', 0) for repo in all_data for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start)
    total_lines_deleted = sum(pr.get('deletions', 0) for repo in all_data for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start)
    
    elements.append(Paragraph("EXECUTIVE SUMMARY", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))
    
    summary_text = f"""This report provides a concise analysis of development activity for the Social Network project 
    across all relevant repositories for Week {week_num} of {year} ({format_date(start)} - {format_date(end - timedelta(days=1))}). 
    Key metrics include code commits, issue resolution, and pull request workflows. During this period, 
    the team collectively made {total_commits} commits and processed a net change of 
    {total_lines_added - total_lines_deleted:+,} lines of code. Active collaboration was observed across 
    {len([r for r in all_data if len(r['commits']) > 0 or len(r['issues']) > 0 or len(r['pull_requests']) > 0])} 
    of {len(REPOS)} monitored project repositories.
    """
    elements.append(Paragraph(summary_text, body_style))
    elements.append(Spacer(1, 0.3*cm))
    
    summary_data = [
        ['METRIC', 'VALUE', 'DESCRIPTION'],
        ['Total Commits', str(total_commits), 'Code commits across all project repositories'],
        ['Issues Created', str(total_issues_created), 'New issues opened within the reporting period'],
        ['Issues Closed', str(total_issues_closed), 'Issues resolved and closed within the reporting period'],
        ['PRs Opened', str(total_prs_opened), 'New pull requests submitted for review'],
        ['PRs Merged', str(total_prs_merged), 'Pull requests merged into main branches'],
        ['Lines Added', f'{total_lines_added:,}', 'Total lines of code added from new PRs'],
        ['Lines Deleted', f'{total_lines_deleted:,}', 'Total lines of code removed from new PRs'],
        ['Net Change', f'{total_lines_added - total_lines_deleted:+,}', 'Net lines of code change from new PRs'],
        ['Active Repos', f'{len([r for r in all_data if len(r["commits"]) > 0 or len(r["issues"]) > 0 or len(r["pull_requests"]) > 0])}/{len(REPOS)}', 'Repositories with recorded activity']
    ]
    
    # Smaller table for summary
    summary_table = Table(summary_data, colWidths=[4*cm, 2.5*cm, 10.5*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9), # Reduced
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')), # Lighter grid
        ('FONTSIZE', (0, 1), (-1, -1), 8), # Reduced
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(summary_table)
    elements.append(PageBreak())
    
    # --- Repository-by-Repository Analysis ---
    for repo_data in all_data:
        repo_name = repo_data['name']
        commits = repo_data['commits']
        issues = repo_data['issues']
        prs = repo_data['pull_requests']
        
        # Filter for activity strictly within the reporting period
        issues_created = [i for i in issues if start <= datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) < end]
        issues_closed = [i for i in issues if i.get('closed_at') and start <= datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) < end]
        issues_updated = [i for i in issues if i['state'] == 'open' and start <= datetime.fromisoformat(i['updated_at'].replace('Z', '+00:00')) < end and i not in issues_created]
        
        prs_opened = [pr for pr in prs if start <= datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) < end]
        prs_merged = [pr for pr in prs if pr.get('merged_at') and start <= datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) < end]
        
        has_activity = len(commits) > 0 or len(issues_created) > 0 or len(issues_closed) > 0 or len(prs_opened) > 0 or len(prs_merged) > 0
        
        # Use KeepTogether to ensure heading and intro paragraph stay on same page
        repo_section_elements = []
        repo_section_elements.append(Paragraph(f"REPOSITORY: {capitalize_repo_name(repo_name).upper()}", heading2_style))
        repo_section_elements.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))
        
        if not has_activity:
            repo_section_elements.append(Paragraph(f"No significant development activity was recorded for the <b>{capitalize_repo_name(repo_name)}</b> repository during this reporting period. This may indicate a stable phase, focused maintenance, or resource allocation to other project priorities.", body_style))
            repo_section_elements.append(Spacer(1, 0.5*cm))
            elements.append(KeepTogether(repo_section_elements))
            elements.append(PageBreak())
            continue
        
        # Repository overview
        repo_lines_added = sum(pr.get('additions', 0) for pr in prs_opened)
        repo_lines_deleted = sum(pr.get('deletions', 0) for pr in prs_opened)
        
        overview_text = f"""The <b>{capitalize_repo_name(repo_name)}</b> repository demonstrated activity this week with 
        {len(commits)} commits, {len(issues_created)} new issues, and {len(prs_opened)} pull requests. 
        These development efforts resulted in {repo_lines_added:,} lines added and {repo_lines_deleted:,} lines removed, 
        yielding a net change of {repo_lines_added - repo_lines_deleted:+,} lines.
        """
        
        repo_section_elements.append(Paragraph(overview_text, body_style))
        repo_section_elements.append(Spacer(1, 0.3*cm))
        
        # Repository metrics table
        repo_stats_data = [
            ['METRIC', 'COUNT', 'DETAILS'],
            ['Commits', str(len(commits)), f'{len(set(c.get("commit", {}).get("author", {}).get("name", "Unknown") for c in commits))} unique contributors'],
            ['Issues Created', str(len(issues_created)), f'{len([i for i in issues_created if i["state"] == "open"])} remain open'],
            ['Issues Closed', str(len(issues_closed)), f'Avg. close time: {format_timedelta(sum([calculate_time_to_close(i) for i in issues_closed if calculate_time_to_close(i)], timedelta()) / len(issues_closed) if issues_closed else None)}'],
            ['Issues Updated', str(len(issues_updated)), 'Existing open issues with activity'],
            ['PRs Opened', str(len(prs_opened)), f'{len([pr for pr in prs_opened if pr["state"] == "open"])} currently open'],
            ['PRs Merged', str(len(prs_merged)), f'{len(prs_merged) / len(prs_opened) * 100:.0f}% merge rate' if prs_opened else 'N/A'],
            ['Code Added', f'{repo_lines_added:,}', 'Total lines added'],
            ['Code Deleted', f'{repo_lines_deleted:,}', 'Total lines removed'],
        ]
        
        # Adjust column widths to be more compact
        repo_stats_table = Table(repo_stats_data, colWidths=[3.5*cm, 2.5*cm, 11*cm])
        repo_stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), SECONDARY_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8), # Reduced
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
            ('FONTSIZE', (0, 1), (-1, -1), 7), # Reduced
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        repo_section_elements.append(repo_stats_table)
        repo_section_elements.append(Spacer(1, 0.4*cm))
        
        elements.append(KeepTogether(repo_section_elements)) # Keep repo overview together
        
        # Detailed Commits Analysis
        if commits:
            elements.append(Paragraph("Commit Activity", heading3_style))
            
            commits_by_author = defaultdict(list)
            for commit in commits:
                author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
                commits_by_author[author].append(commit)
            
            commit_data = [['AUTHOR', 'COMMITS', 'COMMIT MESSAGES (SAMPLE)']]
            for author, author_commits in sorted(commits_by_author.items(), key=lambda x: len(x[1]), reverse=True):
                messages = []
                for commit in author_commits[:3]: # Show fewer sample messages
                    msg = commit.get('commit', {}).get('message', '').split('\n')[0][:50]
                    sha = commit.get('sha', '')[:7]
                    commit_url = commit.get('html_url', '#')
                    # Add hyperlink
                    messages.append(f"<link href='{commit_url}'>[{sha}]</link> {msg}")
                
                msgs_str = '<br/>'.join(messages)
                if len(author_commits) > 3:
                    msgs_str += f'<br/><i>...and {len(author_commits) - 3} more commits</i>'
                
                commit_data.append([
                    Paragraph(author, table_cell_style_small),
                    str(len(author_commits)),
                    Paragraph(msgs_str, ParagraphStyle('SmallCommit', parent=table_cell_style_small, fontSize=6.5, leading=7.5)) # Smaller text for commit messages
                ])
            
            commit_table = Table(commit_data, colWidths=[3.5*cm, 1.5*cm, 12*cm]) # Adjusted width
            commit_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_1),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
                ('TOPPADDING', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            
            elements.append(KeepTogether([commit_table, Spacer(1, 0.3*cm)])) # Keep table and spacer together

        # Detailed Issues Analysis - Created
        if issues_created:
            elements.append(Paragraph("Issues Created This Week", heading3_style))
            
            issues_data = [['#', 'TITLE', 'TYPE', 'PRIORITY', 'CREATOR', 'ASSIGNEES', 'STATUS', 'CREATED']]
            for issue in sorted(issues_created, key=lambda x: x['number'], reverse=True):
                title = issue['title'][:40] + '...' if len(issue['title']) > 40 else issue['title']
                status = 'OPEN' if issue['state'] == 'open' else 'CLOSED'
                assignees = ', '.join([a['login'] for a in issue.get('assignees', [])][:1]) # Fewer assignees for display
                if len(issue.get('assignees', [])) > 1:
                    assignees += f' +{len(issue.get("assignees", [])) - 1}'
                if not assignees:
                    assignees = 'Unassigned'
                
                issue_url = issue.get('html_url', '#')

                issues_data.append([
                    Paragraph(f"<link href='{issue_url}'>#{issue['number']}</link>", table_cell_style_small),
                    Paragraph(title, table_cell_style_small),
                    Paragraph(get_issue_type(issue), table_cell_style_small),
                    Paragraph(get_priority(issue), table_cell_style_small),
                    Paragraph(issue.get('user', {}).get('login', 'N/A')[:12], table_cell_style_small),
                    Paragraph(assignees, table_cell_style_small),
                    Paragraph(status, table_cell_style_small),
                    Paragraph(issue['created_at'][:10], table_cell_style_small)
                ])
            
            # Adjusted colWidths for compactness
            issues_table = Table(issues_data, colWidths=[1.5*cm, 4.5*cm, 1.8*cm, 1.8*cm, 2*cm, 2.5*cm, 1.5*cm, 1.8*cm])
            issues_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (6, 0), (6, -1), 'CENTER'), # Status column
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
                ('TOPPADDING', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            elements.append(KeepTogether([issues_table, Spacer(1, 0.3*cm)]))
        
        # Detailed Issues Analysis - Closed
        if issues_closed:
            elements.append(Paragraph("Issues Closed This Week", heading3_style))
            
            closed_data = [['#', 'TITLE', 'TYPE', 'CLOSED BY', 'TIME TO CLOSE', 'CLOSED DATE']]
            for issue in sorted(issues_closed, key=lambda x: x['number'], reverse=True):
                title = issue['title'][:45] + '...' if len(issue['title']) > 45 else issue['title']
                closed_by = issue.get('closed_by', {}).get('login', 'N/A') if issue.get('closed_by') else 'N/A'
                issue_url = issue.get('html_url', '#')

                closed_data.append([
                    Paragraph(f"<link href='{issue_url}'>#{issue['number']}</link>", table_cell_style_small),
                    Paragraph(title, table_cell_style_small),
                    Paragraph(get_issue_type(issue), table_cell_style_small),
                    Paragraph(closed_by[:15], table_cell_style_small),
                    Paragraph(format_timedelta(calculate_time_to_close(issue)), table_cell_style_small),
                    Paragraph(issue['closed_at'][:10], table_cell_style_small)
                ])
            
            # Adjusted colWidths for compactness
            closed_table = Table(closed_data, colWidths=[1.5*cm, 5.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            closed_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
                ('TOPPADDING', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            elements.append(KeepTogether([closed_table, Spacer(1, 0.3*cm)]))
        
        # Pull Requests Analysis - Opened
        if prs_opened:
            elements.append(Paragraph("Pull Requests Opened This Week", heading3_style))
            
            prs_data = [['#', 'TITLE', 'AUTHOR', 'STATUS', 'CHANGES', 'REVIEWERS', 'CREATED']]
            for pr in sorted(prs_opened, key=lambda x: x['number'], reverse=True):
                title = pr['title'][:40] + '...' if len(pr['title']) > 40 else pr['title']
                
                if pr.get('merged_at'):
                    status = 'MERGED'
                elif pr['state'] == 'open':
                    status = 'OPEN'
                else:
                    status = 'CLOSED'
                
                changes = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                
                reviewers = []
                if pr.get('requested_reviewers'):
                    reviewers = [r['login'] for r in pr['requested_reviewers'][:1]] # Fewer reviewers for display
                reviewers_str = ', '.join(reviewers) if reviewers else 'None'
                if len(pr.get('requested_reviewers', [])) > 1:
                    reviewers_str += f' +{len(pr.get("requested_reviewers", [])) - 1}'
                
                pr_url = pr.get('html_url', '#')

                prs_data.append([
                    Paragraph(f"<link href='{pr_url}'>#{pr['number']}</link>", table_cell_style_small),
                    Paragraph(title, table_cell_style_small),
                    Paragraph(pr.get('user', {}).get('login', 'N/A')[:12], table_cell_style_small),
                    Paragraph(status, table_cell_style_small),
                    Paragraph(changes, table_cell_style_small),
                    Paragraph(reviewers_str, table_cell_style_small),
                    Paragraph(pr['created_at'][:10], table_cell_style_small)
                ])
            
            # Adjusted colWidths for compactness
            prs_table = Table(prs_data, colWidths=[1.5*cm, 4.8*cm, 2.3*cm, 1.8*cm, 2*cm, 2.7*cm, 2.2*cm])
            prs_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
                ('TOPPADDING', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            elements.append(KeepTogether([prs_table, Spacer(1, 0.3*cm)]))
        
        # Merged PRs Detail
        if prs_merged:
            elements.append(Paragraph("Pull Requests Merged This Week", heading3_style))
            
            merged_data = [['#', 'TITLE', 'AUTHOR', 'MERGED BY', 'LINES CHANGED', 'MERGED DATE']]
            for pr in sorted(prs_merged, key=lambda x: x['merged_at'] if x.get('merged_at') else '', reverse=True):
                title = pr['title'][:45] + '...' if len(pr['title']) > 45 else pr['title']
                merged_by = pr.get('merged_by', {}).get('login', 'N/A') if pr.get('merged_by') else pr.get('user', {}).get('login', 'N/A')
                lines_changed = f"+{pr.get('additions', 0)} -{pr.get('deletions', 0)}"
                pr_url = pr.get('html_url', '#')

                merged_data.append([
                    Paragraph(f"<link href='{pr_url}'>#{pr['number']}</link>", table_cell_style_small),
                    Paragraph(title, table_cell_style_small),
                    Paragraph(pr.get('user', {}).get('login', 'N/A')[:12], table_cell_style_small),
                    Paragraph(merged_by[:12], table_cell_style_small),
                    Paragraph(lines_changed, table_cell_style_small),
                    Paragraph(pr['merged_at'][:10] if pr.get('merged_at') else 'N/A', table_cell_style_small)
                ])
            
            # Adjusted colWidths for compactness
            merged_table = Table(merged_data, colWidths=[1.5*cm, 5.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            merged_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
                ('TOPPADDING', (0, 0), (-1, 0), 7),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            elements.append(KeepTogether([merged_table, Spacer(1, 0.3*cm)]))
        
        elements.append(PageBreak())
    
    # --- Team Performance Analysis ---
    elements.append(Paragraph("TEAM PERFORMANCE ANALYSIS", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))
    
    team_text = """This section provides a summary of individual team member contributions across all repositories. 
    Metrics include commit activity, issue management, pull request activity, and code volume changes. This data helps 
    in understanding workload distribution and overall team engagement during the reporting period.
    """
    
    elements.append(Paragraph(team_text, body_style))
    elements.append(Spacer(1, 0.3*cm))
    
    team_stats = defaultdict(lambda: {
        'commits': 0,
        'issues_created': 0,
        'issues_closed': 0,
        'prs_opened': 0,
        'prs_merged': 0,
        'lines_added': 0,
        'lines_deleted': 0,
        'repos': set()
    })
    
    for repo_data in all_data:
        repo_name = repo_data['name']
        
        for commit in repo_data['commits']:
            author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
            team_stats[author]['commits'] += 1
            team_stats[author]['repos'].add(capitalize_repo_name(repo_name))
        
        for issue in repo_data['issues']:
            if start <= datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00')) < end:
                creator = issue.get('user', {}).get('login', 'unknown')
                team_stats[creator]['issues_created'] += 1
                team_stats[creator]['repos'].add(capitalize_repo_name(repo_name))
            
            if issue.get('closed_at') and start <= datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00')) < end:
                if issue.get('closed_by'):
                    closer = issue['closed_by'].get('login', 'unknown')
                    team_stats[closer]['issues_closed'] += 1
                    team_stats[closer]['repos'].add(capitalize_repo_name(repo_name))
        
        for pr in repo_data['pull_requests']:
            if start <= datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) < end:
                author = pr.get('user', {}).get('login', 'unknown')
                team_stats[author]['prs_opened'] += 1
                team_stats[author]['lines_added'] += pr.get('additions', 0)
                team_stats[author]['lines_deleted'] += pr.get('deletions', 0)
                team_stats[author]['repos'].add(capitalize_repo_name(repo_name))
            
            if pr.get('merged_at') and start <= datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) < end:
                merger = pr.get('merged_by', {}).get('login', 'unknown') if pr.get('merged_by') else pr.get('user', {}).get('login', 'unknown')
                team_stats[merger]['prs_merged'] += 1
                team_stats[merger]['repos'].add(capitalize_repo_name(repo_name))
    
    team_data = [['TEAM MEMBER', 'COMMITS', 'ISSUES\nCREATED', 'ISSUES\nCLOSED', 'PRS\nOPENED', 'PRS\nMERGED', 'LINES\nADDED', 'LINES\nDELETED', 'ACTIVE\nREPOS']]
    
    sorted_team = sorted(
        team_stats.items(),
        key=lambda x: x[1]['commits'] + x[1]['prs_opened'] + x[1]['issues_created'],
        reverse=True
    )
    
    for member, stats in sorted_team:
        if stats['commits'] == 0 and stats['issues_created'] == 0 and stats['prs_opened'] == 0 and stats['prs_merged'] == 0:
            continue
        
        repos_str = ', '.join(sorted(stats['repos']))
        if len(repos_str) > 30:
            repos_str = repos_str[:27] + '...' # Truncate for display
        
        team_data.append([
            Paragraph(member[:18], table_cell_style_small),
            str(stats['commits']),
            str(stats['issues_created']),
            str(stats['issues_closed']),
            str(stats['prs_opened']),
            str(stats['prs_merged']),
            f"{stats['lines_added']:,}",
            f"{stats['lines_deleted']:,}",
            Paragraph(repos_str, ParagraphStyle('TinyRepos', parent=table_cell_style_small, fontSize=6))
        ])
    
    # Adjusted colWidths for compactness
    team_table = Table(team_data, colWidths=[3*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.4*cm, 1.7*cm, 1.7*cm, 3*cm])
    team_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 7),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    
    elements.append(KeepTogether([team_table, Spacer(1, 0.5*cm)]))
    
    # --- Project Health Metrics ---
    elements.append(PageBreak())
    elements.append(Paragraph("PROJECT HEALTH METRICS", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))
    
    health_text = """The following metrics provide insights into project health, highlighting potential areas 
    for attention. Regular monitoring of these indicators is crucial for maintaining development velocity and code quality."""
    
    elements.append(Paragraph(health_text, body_style))
    elements.append(Spacer(1, 0.3*cm))
    
    all_open_issues = [i for repo in all_data for i in repo['issues'] if i['state'] == 'open']
    blocked_issues = [i for i in all_open_issues if any('block' in l['name'].lower() or 'waiting' in l['name'].lower() for l in i.get('labels', []))]
    unassigned_issues = [i for i in all_open_issues if not i.get('assignees')]
    high_priority_open = [i for i in all_open_issues if any(p in l['name'].lower() for l in i.get('labels', []) for p in ['critical', 'high', 'p0', 'p1'])]
    
    open_prs = [pr for repo in all_data for pr in repo['pull_requests'] if pr['state'] == 'open' and not pr.get('merged_at')] # Only truly open, not merged but still 'open' state
    stale_prs = [pr for pr in open_prs if (datetime.now(timezone.utc) - datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))).days > 7]
    
    def get_health_status(value, thresholds):
        # thresholds = (Good_max, Acceptable_max)
        if value <= thresholds[0]:
            return 'HEALTHY', colors.HexColor('#2E7D32') # Dark Green
        elif value <= thresholds[1]:
            return 'CAUTION', colors.HexColor('#FFB300') # Amber
        else:
            return 'CRITICAL', colors.HexColor('#D32F2F') # Dark Red
    
    health_metrics_data = [
        ('Total Open Issues', len(all_open_issues), (15, 25), 'Issues awaiting resolution'),
        ('Blocked Issues', len(blocked_issues), (1, 3), 'Issues with blockers or dependencies'), # Adjusted thresholds
        ('Unassigned Issues', len(unassigned_issues), (2, 5), 'Issues without assigned developers'), # Adjusted thresholds
        ('High Priority Open', len(high_priority_open), (1, 3), 'Critical/high priority unresolved'), # Adjusted thresholds
        ('Open Pull Requests', len(open_prs), (8, 15), 'PRs awaiting review/merge'),
        ('Stale PRs (>7 days)', len(stale_prs), (1, 3), 'PRs without recent activity'), # Adjusted thresholds
    ]
    
    health_data = [['METRIC', 'VALUE', 'STATUS', 'ASSESSMENT']]
    health_status_colors = []
    
    for metric_name, value, thresholds, assessment in health_metrics_data:
        status_text, status_color = get_health_status(value, thresholds)
        health_data.append([metric_name, str(value), status_text, assessment])
        health_status_colors.append(status_color)
    
    health_table = Table(health_data, colWidths=[4*cm, 2*cm, 2.5*cm, 8.5*cm]) # Adjusted widths
    
    health_style = [
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (2, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
    ]
    
    for i, status_color in enumerate(health_status_colors, 1):
        health_style.append(('BACKGROUND', (2, i), (2, i), status_color))
        health_style.append(('TEXTCOLOR', (2, i), (2, i), colors.white))
    
    health_table.setStyle(TableStyle(health_style))
    
    elements.append(KeepTogether([health_table, Spacer(1, 0.5*cm)]))
    
    # Recommendations section
    elements.append(Paragraph("Recommendations & Action Items", heading3_style))
    
    recommendations = []
    if len(blocked_issues) > health_metrics_data[1][2][0]: # Check against healthy threshold
        recommendations.append(f"• Prioritize resolving {len(blocked_issues)} blocked issue(s) to unblock dependent tasks.")
    if len(unassigned_issues) > health_metrics_data[2][2][0]:
        recommendations.append(f"• Assign owners to {len(unassigned_issues)} unassigned issues to ensure accountability.")
    if len(high_priority_open) > health_metrics_data[3][2][0]:
        recommendations.append(f"• Expedite resolution of {len(high_priority_open)} high-priority open issues.")
    if len(stale_prs) > health_metrics_data[5][2][0]:
        recommendations.append(f"• Conduct timely reviews and action {len(stale_prs)} stale pull request(s) to maintain development flow.")
    if total_prs_opened > 0 and total_prs_merged / total_prs_opened < 0.7: # Custom threshold for merge rate
        recommendations.append(f"• Improve PR merge rate (currently {total_prs_merged/total_prs_opened*100:.0f}%) through faster reviews and smaller PRs.")
    if total_commits == 0 and total_issues_created == 0 and total_prs_opened == 0:
        recommendations.append("• Overall project activity is low; assess team focus and potential roadblocks.")
    
    if not recommendations:
        recommendations.append("• Project health metrics are generally within acceptable ranges. Continue current practices.")
    
    for rec in recommendations:
        elements.append(Paragraph(rec, body_style))
    
    elements.append(Spacer(1, 0.5*cm))
    
    # --- Footer ---
    elements.append(Spacer(1, 1*cm))
    footer_text = f"""<i>This automated report was generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} 
    for the <b>{ORG_NAME}</b> Social Network Project. Data covers Week {week_num} of {year} 
    ({format_date(start)} through {format_date(end - timedelta(days=1))}).
    </i>"""
    elements.append(Paragraph(footer_text, meta_style))
    
    # Build PDF
    doc.build(elements)
    print(f"✓ Professional PDF report generated: reports/{filename}")
    
    # Also update latest
    latest_path = reports_dir / 'latest.pdf'
    import shutil
    shutil.copy(str(filepath), str(latest_path))
    print(f"✓ Latest report updated: reports/latest.pdf")

# The main function remains the same as it primarily orchestrates the data fetching and report generation
def main():
    print("=" * 70)
    print("PROFESSIONAL WEEKLY PROGRESS REPORT GENERATOR (Social Network Project)")
    print("=" * 70)
    print(f"\nOrganization: {ORG_NAME}")
    print(f"Monitored Repositories: {', '.join([capitalize_repo_name(r) for r in REPOS])}\n")
    
    global start, end
    start, end = get_week_range()
    print(f"Reporting Period: {format_date(start)} to {format_date(end - timedelta(days=1))}\n")
    print("=" * 70)
    
    all_data = []
    
    for repo in REPOS:
        print(f"\n[{capitalize_repo_name(repo)}] Fetching repository data...")
        activity = fetch_repo_activity(repo, start, end)
        
        all_data.append({
            'name': repo,
            'commits': activity['commits'],
            'issues': activity['issues'],
            'pull_requests': activity['pull_requests']
        })
    
    print("\n" + "=" * 70)
    print("Generating comprehensive professional PDF report...")
    print("=" * 70)
    generate_pdf_report(all_data, (start, end))
    
    print("\n" + "=" * 70)
    print("REPORT GENERATION COMPLETE")
    print("=" * 70)

if __name__ == '__main__':
    main()