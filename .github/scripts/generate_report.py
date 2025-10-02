#!/usr/bin/env python3

import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import requests
from pathlib import Path

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
ORG_NAME = os.environ.get('ORG_NAME')
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

def get_week_range():
    """Get start and end dates for the specified or current week"""
    if WEEK_NUMBER:
        week_num = int(WEEK_NUMBER)
        year = int(YEAR) if YEAR else datetime.now(timezone.utc).year
        
        jan_1 = datetime(year, 1, 1, tzinfo=timezone.utc)
        days_to_monday = (7 - jan_1.weekday()) % 7
        if jan_1.weekday() > 3:
            days_to_monday += 7
        
        first_monday = jan_1 + timedelta(days=days_to_monday)
        start = first_monday + timedelta(weeks=week_num - 1)
        end = start + timedelta(days=7)
        
        print(f"Using manually specified week: {week_num}, {year}")
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        week_num = end.isocalendar()[1]
        year = end.year
        print(f"Using current week: {week_num}, {year}")
    
    return start, end

def format_date(date):
    """Format date as YYYY-MM-DD"""
    return date.strftime('%Y-%m-%d')

def format_datetime(dt_str):
    """Format datetime string"""
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return dt.strftime('%Y-%m-%d %H:%M UTC')

def capitalize_repo_name(repo_name):
    """Properly capitalize repository names"""
    return repo_name.capitalize()

def github_api_get(url, params=None):
    """Make GET request to GitHub API"""
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"API Error for {url}: {e}")
        return [] if "list" in url else {}

def fetch_repo_activity(repo, start, end):
    """Fetch all activity for a repository in the date range"""
    print(f"  Fetching activity for {repo}...")
    
    commits_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/commits'
    commits_params = {'since': start.isoformat(), 'until': end.isoformat(), 'per_page': 100}
    commits = github_api_get(commits_url, commits_params)
    if not isinstance(commits, list):
        commits = []
    
    issues_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues'
    issues_params = {'state': 'all', 'since': start.isoformat(), 'per_page': 100}
    all_issues = github_api_get(issues_url, issues_params)
    if not isinstance(all_issues, list):
        all_issues = []
    
    issues = []
    for item in all_issues:
        if 'pull_request' in item:
            continue
        
        created = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
        updated = datetime.fromisoformat(item['updated_at'].replace('Z', '+00:00'))
        closed = datetime.fromisoformat(item['closed_at'].replace('Z', '+00:00')) if item.get('closed_at') else None
        
        if created >= start or updated >= start or (closed and closed >= start):
            issues.append(item)
    
    prs_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls'
    prs_params = {'state': 'all', 'sort': 'updated', 'direction': 'desc', 'per_page': 100}
    all_prs = github_api_get(prs_url, prs_params)
    if not isinstance(all_prs, list):
        all_prs = []
    
    prs = []
    for pr in all_prs:
        created = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
        updated = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
        merged = datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) if pr.get('merged_at') else None
        closed = datetime.fromisoformat(pr['closed_at'].replace('Z', '+00:00')) if pr.get('closed_at') else None
        
        if created >= start or updated >= start or (merged and merged >= start) or (closed and closed >= start):
            prs.append(pr)
    
    print(f"    Found: {len(commits)} commits, {len(issues)} issues, {len(prs)} PRs")
    
    return {
        'commits': commits,
        'issues': issues,
        'pull_requests': prs
    }

def get_issue_type(issue):
    """Determine issue type from labels"""
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
    """Extract priority from labels"""
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
    """Calculate time from creation to closure"""
    if not issue.get('closed_at'):
        return None
    
    created = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
    closed = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
    delta = closed - created
    
    return delta

def format_timedelta(delta):
    """Format timedelta as readable string"""
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

def generate_pdf_report(all_data, week_range):
    """Generate comprehensive professional PDF report"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    
    start, end = week_range
    week_num = end.isocalendar()[1]
    year = end.year
    
    # Create PDF
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    filename = f"week_{week_num}_{year}.pdf"
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
    
    # Professional color scheme
    PRIMARY_COLOR = colors.HexColor('#2C3E50')
    SECONDARY_COLOR = colors.HexColor('#34495E')
    ACCENT_COLOR = colors.HexColor('#3498DB')
    HEADER_BG = colors.HexColor('#ECF0F1')
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=PRIMARY_COLOR,
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=34
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=14,
        textColor=SECONDARY_COLOR,
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    meta_style = ParagraphStyle(
        'MetaInfo',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#7F8C8D'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=PRIMARY_COLOR,
        spaceAfter=10,
        spaceBefore=20,
        fontName='Helvetica-Bold',
        borderWidth=0,
        borderColor=ACCENT_COLOR,
        borderPadding=0,
        leftIndent=0
    )
    
    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=SECONDARY_COLOR,
        spaceAfter=8,
        spaceBefore=14,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#2C3E50'),
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        leading=14
    )
    
    # Title Page
    elements.append(Spacer(1, 2*cm))
    elements.append(Paragraph("WEEKLY PROGRESS REPORT", title_style))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"Week {week_num}, {year}", subtitle_style))
    elements.append(Spacer(1, 0.8*cm))
    
    elements.append(HRFlowable(width="80%", thickness=2, color=ACCENT_COLOR, spaceAfter=0.8*cm, spaceBefore=0))
    
    elements.append(Paragraph(f"<b>Organization:</b> {ORG_NAME}", subtitle_style))
    elements.append(Paragraph(f"<b>Reporting Period:</b> {format_date(start)} to {format_date(end)}", subtitle_style))
    elements.append(Spacer(1, 0.5*cm))
    elements.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}", meta_style))
    
    elements.append(PageBreak())
    
    # Calculate comprehensive totals
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_issues_created = sum(len([i for i in repo['issues'] if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_opened = sum(len([pr for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    
    total_lines_added = sum(pr.get('additions', 0) for repo in all_data for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start)
    total_lines_deleted = sum(pr.get('deletions', 0) for repo in all_data for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start)
    
    # Executive Summary
    elements.append(Paragraph("EXECUTIVE SUMMARY", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT_COLOR, spaceAfter=12, spaceBefore=0))
    
    summary_text = f"""This report provides a comprehensive analysis of development activity across all repositories 
    for Week {week_num} of {year}. The data encompasses commit activity, issue tracking, pull request management, 
    and team contributions. Analysis shows activity across {len([r for r in all_data if len(r['commits']) > 0 or len(r['issues']) > 0 or len(r['pull_requests']) > 0])} 
    of {len(REPOS)} monitored repositories with a total of {total_commits} commits and {total_lines_added + total_lines_deleted} 
    lines of code changed."""
    
    elements.append(Paragraph(summary_text, body_style))
    elements.append(Spacer(1, 0.4*cm))
    
    summary_data = [
        ['METRIC', 'VALUE', 'DESCRIPTION'],
        ['Total Commits', str(total_commits), 'Code commits across all repositories'],
        ['Issues Created', str(total_issues_created), 'New issues opened this week'],
        ['Issues Closed', str(total_issues_closed), 'Issues resolved and closed'],
        ['Pull Requests Opened', str(total_prs_opened), 'New PRs submitted for review'],
        ['Pull Requests Merged', str(total_prs_merged), 'PRs merged into main branches'],
        ['Lines Added', f'{total_lines_added:,}', 'Total lines of code added'],
        ['Lines Deleted', f'{total_lines_deleted:,}', 'Total lines of code removed'],
        ['Net Change', f'{total_lines_added - total_lines_deleted:+,}', 'Net lines of code change'],
        ['Active Repositories', f'{len([r for r in all_data if len(r["commits"]) > 0 or len(r["issues"]) > 0 or len(r["pull_requests"]) > 0])}/{len(REPOS)}', 'Repositories with activity']
    ]
    
    summary_table = Table(summary_data, colWidths=[4*cm, 3*cm, 10*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(summary_table)
    elements.append(PageBreak())
    
    # Repository-by-Repository Analysis
    for repo_data in all_data:
        repo_name = repo_data['name']
        commits = repo_data['commits']
        issues = repo_data['issues']
        prs = repo_data['pull_requests']
        
        issues_created = [i for i in issues if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]
        issues_closed = [i for i in issues if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]
        issues_updated = [i for i in issues if i['state'] == 'open' and i not in issues_created]
        prs_opened = [pr for pr in prs if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]
        prs_merged = [pr for pr in prs if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]
        
        has_activity = len(commits) > 0 or len(issues_created) > 0 or len(issues_closed) > 0 or len(prs_opened) > 0 or len(prs_merged) > 0
        
        elements.append(Paragraph(f"REPOSITORY: {capitalize_repo_name(repo_name).upper()}", heading2_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT_COLOR, spaceAfter=12, spaceBefore=0))
        
        if not has_activity:
            elements.append(Paragraph("No development activity was recorded for this repository during the reporting period. "
                                    "This may indicate a maintenance phase, planned downtime, or resource allocation to other priorities.",
                                    body_style))
            elements.append(Spacer(1, 0.5*cm))
            continue
        
        # Repository overview
        repo_lines_added = sum(pr.get('additions', 0) for pr in prs_opened)
        repo_lines_deleted = sum(pr.get('deletions', 0) for pr in prs_opened)
        
        overview_text = f"""The {capitalize_repo_name(repo_name)} repository showed significant activity this week with {len(commits)} commits, 
        {len(issues_created)} new issues, and {len(prs_opened)} pull requests. Development efforts resulted in {repo_lines_added:,} lines added 
        and {repo_lines_deleted:,} lines removed, representing a net change of {repo_lines_added - repo_lines_deleted:+,} lines."""
        
        elements.append(Paragraph(overview_text, body_style))
        elements.append(Spacer(1, 0.3*cm))
        
        # Repository metrics table
        repo_stats_data = [
            ['METRIC', 'COUNT', 'DETAILS'],
            ['Commits', str(len(commits)), f'{len(set(c.get("commit", {}).get("author", {}).get("name", "Unknown") for c in commits))} unique contributors'],
            ['Issues Created', str(len(issues_created)), f'{len([i for i in issues_created if i["state"] == "open"])} remain open'],
            ['Issues Closed', str(len(issues_closed)), f'Average close time: {format_timedelta(sum([calculate_time_to_close(i) for i in issues_closed if calculate_time_to_close(i)], timedelta()) / len(issues_closed) if issues_closed else None)}'],
            ['Issues Updated', str(len(issues_updated)), 'Existing open issues with activity'],
            ['PRs Opened', str(len(prs_opened)), f'{len([pr for pr in prs_opened if pr["state"] == "open"])} currently open'],
            ['PRs Merged', str(len(prs_merged)), f'{len(prs_merged) / len(prs_opened) * 100:.0f}% merge rate' if prs_opened else 'N/A'],
            ['Code Added', f'{repo_lines_added:,}', 'Total lines added'],
            ['Code Deleted', f'{repo_lines_deleted:,}', 'Total lines removed'],
        ]
        
        repo_stats_table = Table(repo_stats_data, colWidths=[4*cm, 3*cm, 10*cm])
        repo_stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), SECONDARY_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(repo_stats_table)
        elements.append(Spacer(1, 0.4*cm))
        
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
                for commit in author_commits[:5]:
                    msg = commit.get('commit', {}).get('message', '').split('\n')[0][:60]
                    sha = commit.get('sha', '')[:7]
                    date = commit.get('commit', {}).get('author', {}).get('date', '')[:10]
                    messages.append(f"[{sha}] {msg} ({date})")
                
                msgs_str = '<br/>'.join(messages)
                if len(author_commits) > 5:
                    msgs_str += f'<br/><i>...and {len(author_commits) - 5} more commits</i>'
                
                commit_data.append([
                    Paragraph(author, body_style),
                    str(len(author_commits)),
                    Paragraph(msgs_str, ParagraphStyle('Small', parent=body_style, fontSize=7, leading=10))
                ])
            
            commit_table = Table(commit_data, colWidths=[4*cm, 2*cm, 11*cm])
            commit_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16A085')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            
            elements.append(commit_table)
            elements.append(Spacer(1, 0.3*cm))
        
        # Detailed Issues Analysis
        if issues_created:
            elements.append(Paragraph("Issues Created This Week", heading3_style))
            
            issues_data = [['#', 'TITLE', 'TYPE', 'PRIORITY', 'CREATOR', 'ASSIGNEES', 'STATUS', 'CREATED']]
            for issue in sorted(issues_created, key=lambda x: x['number'], reverse=True):
                title = issue['title'][:50] + '...' if len(issue['title']) > 50 else issue['title']
                status = 'OPEN' if issue['state'] == 'open' else 'CLOSED'
                assignees = ', '.join([a['login'] for a in issue.get('assignees', [])][:2])
                if len(issue.get('assignees', [])) > 2:
                    assignees += f' +{len(issue.get("assignees", [])) - 2}'
                if not assignees:
                    assignees = 'Unassigned'
                
                labels_text = ', '.join([l['name'] for l in issue.get('labels', [])][:2])
                
                issues_data.append([
                    f"#{issue['number']}",
                    Paragraph(title, ParagraphStyle('Small', parent=body_style, fontSize=7)),
                    get_issue_type(issue),
                    get_priority(issue),
                    issue.get('user', {}).get('login', 'N/A')[:12],
                    Paragraph(assignees, ParagraphStyle('Small', parent=body_style, fontSize=7)),
                    status,
                    issue['created_at'][:10]
                ])
            
            issues_table = Table(issues_data, colWidths=[1.2*cm, 5*cm, 2*cm, 1.8*cm, 2*cm, 2.5*cm, 1.5*cm, 2*cm])
            issues_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E74C3C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(issues_table)
            elements.append(Spacer(1, 0.3*cm))
        
        # Closed Issues Analysis
        if issues_closed:
            elements.append(Paragraph("Issues Closed This Week", heading3_style))
            
            closed_data = [['#', 'TITLE', 'TYPE', 'CLOSED BY', 'TIME TO CLOSE', 'CLOSED DATE']]
            for issue in sorted(issues_closed, key=lambda x: x['number'], reverse=True):
                title = issue['title'][:55] + '...' if len(issue['title']) > 55 else issue['title']
                closed_by = issue.get('closed_by', {}).get('login', 'N/A') if issue.get('closed_by') else 'N/A'
                
                closed_data.append([
                    f"#{issue['number']}",
                    Paragraph(title, ParagraphStyle('Small', parent=body_style, fontSize=7)),
                    get_issue_type(issue),
                    closed_by[:15],
                    format_timedelta(calculate_time_to_close(issue)),
                    issue['closed_at'][:10]
                ])
            
            closed_table = Table(closed_data, colWidths=[1.2*cm, 6.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.8*cm])
            closed_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27AE60')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(closed_table)
            elements.append(Spacer(1, 0.3*cm))
        
        # Pull Requests Analysis
        if prs_opened:
            elements.append(Paragraph("Pull Requests Opened This Week", heading3_style))
            
            prs_data = [['#', 'TITLE', 'AUTHOR', 'STATUS', 'CHANGES', 'REVIEWERS', 'CREATED']]
            for pr in sorted(prs_opened, key=lambda x: x['number'], reverse=True):
                title = pr['title'][:50] + '...' if len(pr['title']) > 50 else pr['title']
                
                if pr.get('merged_at'):
                    status = 'MERGED'
                elif pr['state'] == 'open':
                    status = 'OPEN'
                else:
                    status = 'CLOSED'
                
                changes = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                
                reviewers = []
                if pr.get('requested_reviewers'):
                    reviewers = [r['login'] for r in pr['requested_reviewers'][:2]]
                reviewers_str = ', '.join(reviewers) if reviewers else 'None'
                if len(pr.get('requested_reviewers', [])) > 2:
                    reviewers_str += f' +{len(pr.get("requested_reviewers", [])) - 2}'
                
                prs_data.append([
                    f"#{pr['number']}",
                    Paragraph(title, ParagraphStyle('Small', parent=body_style, fontSize=7)),
                    pr.get('user', {}).get('login', 'N/A')[:12],
                    status,
                    changes,
                    Paragraph(reviewers_str, ParagraphStyle('Small', parent=body_style, fontSize=7)),
                    pr['created_at'][:10]
                ])
            
            prs_table = Table(prs_data, colWidths=[1.2*cm, 5.5*cm, 2.3*cm, 1.8*cm, 2*cm, 2.7*cm, 2.5*cm])
            prs_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9B59B6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(prs_table)
            elements.append(Spacer(1, 0.3*cm))
        
        # Merged PRs Detail
        if prs_merged:
            elements.append(Paragraph("Pull Requests Merged This Week", heading3_style))
            
            merged_data = [['#', 'TITLE', 'AUTHOR', 'MERGED BY', 'LINES CHANGED', 'MERGED DATE']]
            for pr in sorted(prs_merged, key=lambda x: x['merged_at'] if x.get('merged_at') else '', reverse=True):
                title = pr['title'][:55] + '...' if len(pr['title']) > 55 else pr['title']
                merged_by = pr.get('merged_by', {}).get('login', 'N/A') if pr.get('merged_by') else 'N/A'
                lines_changed = f"+{pr.get('additions', 0)} -{pr.get('deletions', 0)}"
                
                merged_data.append([
                    f"#{pr['number']}",
                    Paragraph(title, ParagraphStyle('Small', parent=body_style, fontSize=7)),
                    pr.get('user', {}).get('login', 'N/A')[:12],
                    merged_by[:12],
                    lines_changed,
                    pr['merged_at'][:10] if pr.get('merged_at') else 'N/A'
                ])
            
            merged_table = Table(merged_data, colWidths=[1.2*cm, 6.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.8*cm])
            merged_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1ABC9C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(merged_table)
            elements.append(Spacer(1, 0.3*cm))
        
        elements.append(PageBreak())
    
    # Team Performance Analysis
    elements.append(Paragraph("TEAM PERFORMANCE ANALYSIS", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT_COLOR, spaceAfter=12, spaceBefore=0))
    
    team_text = """This section provides a detailed breakdown of individual team member contributions across all repositories. 
    Metrics include commit activity, issue management, pull request activity, and code volume changes. This data is essential 
    for understanding workload distribution, identifying high performers, and ensuring balanced team collaboration."""
    
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
            if datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00')) >= start:
                creator = issue.get('user', {}).get('login', 'unknown')
                team_stats[creator]['issues_created'] += 1
                team_stats[creator]['repos'].add(capitalize_repo_name(repo_name))
            
            if issue.get('closed_at') and datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00')) >= start:
                if issue.get('closed_by'):
                    closer = issue['closed_by'].get('login', 'unknown')
                    team_stats[closer]['issues_closed'] += 1
                    team_stats[closer]['repos'].add(capitalize_repo_name(repo_name))
        
        for pr in repo_data['pull_requests']:
            if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start:
                author = pr.get('user', {}).get('login', 'unknown')
                team_stats[author]['prs_opened'] += 1
                team_stats[author]['lines_added'] += pr.get('additions', 0)
                team_stats[author]['lines_deleted'] += pr.get('deletions', 0)
                team_stats[author]['repos'].add(capitalize_repo_name(repo_name))
            
            if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start:
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
        if stats['commits'] == 0 and stats['issues_created'] == 0 and stats['prs_opened'] == 0:
            continue
        
        repos_str = ', '.join(sorted(stats['repos']))[:30]
        if len(', '.join(sorted(stats['repos']))) > 30:
            repos_str += '...'
        
        team_data.append([
            member[:18],
            str(stats['commits']),
            str(stats['issues_created']),
            str(stats['issues_closed']),
            str(stats['prs_opened']),
            str(stats['prs_merged']),
            f"{stats['lines_added']:,}",
            f"{stats['lines_deleted']:,}",
            Paragraph(repos_str, ParagraphStyle('Tiny', parent=body_style, fontSize=6))
        ])
    
    team_table = Table(team_data, colWidths=[3.3*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.8*cm, 1.8*cm, 2.6*cm])
    team_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
        ('TOPPADDING', (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(team_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Sprint Health Metrics
    elements.append(PageBreak())
    elements.append(Paragraph("PROJECT HEALTH METRICS", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=ACCENT_COLOR, spaceAfter=12, spaceBefore=0))
    
    health_text = """The following metrics provide insights into project health, highlighting potential bottlenecks, 
    resource allocation issues, and areas requiring management attention. Regular monitoring of these indicators 
    is crucial for maintaining development velocity and code quality."""
    
    elements.append(Paragraph(health_text, body_style))
    elements.append(Spacer(1, 0.3*cm))
    
    all_open_issues = [i for repo in all_data for i in repo['issues'] if i['state'] == 'open']
    blocked_issues = [i for i in all_open_issues if any('block' in l['name'].lower() or 'waiting' in l['name'].lower() for l in i.get('labels', []))]
    unassigned_issues = [i for i in all_open_issues if not i.get('assignees')]
    high_priority_open = [i for i in all_open_issues if any('critical' in l['name'].lower() or 'high' in l['name'].lower() or 'p0' in l['name'].lower() or 'p1' in l['name'].lower() for l in i.get('labels', []))]
    
    open_prs = [pr for repo in all_data for pr in repo['pull_requests'] if pr['state'] == 'open']
    stale_prs = [pr for pr in open_prs if (datetime.now(timezone.utc) - datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))).days > 7]
    
    def get_health_status(value, thresholds):
        if value <= thresholds[0]:
            return 'HEALTHY', colors.HexColor('#27AE60')
        elif value <= thresholds[1]:
            return 'ACCEPTABLE', colors.HexColor('#F39C12')
        else:
            return 'CRITICAL', colors.HexColor('#E74C3C')
    
    health_data = [
        ['METRIC', 'VALUE', 'STATUS', 'ASSESSMENT'],
        ['Total Open Issues', str(len(all_open_issues)), *get_health_status(len(all_open_issues), (15, 25)), 'Issues awaiting resolution'],
        ['Blocked Issues', str(len(blocked_issues)), *get_health_status(len(blocked_issues), (0, 2)), 'Issues with blockers or dependencies'],
        ['Unassigned Issues', str(len(unassigned_issues)), *get_health_status(len(unassigned_issues), (3, 8)), 'Issues without assigned developers'],
        ['High Priority Open', str(len(high_priority_open)), *get_health_status(len(high_priority_open), (2, 5)), 'Critical/high priority unresolved'],
        ['Open Pull Requests', str(len(open_prs)), *get_health_status(len(open_prs), (8, 15)), 'PRs awaiting review/merge'],
        ['Stale PRs (>7 days)', str(len(stale_prs)), *get_health_status(len(stale_prs), (0, 3)), 'PRs without recent activity'],
    ]
    
    health_table = Table(health_data, colWidths=[4.5*cm, 2.5*cm, 3*cm, 7*cm])
    
    # Build health table style dynamically
    health_style = [
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (2, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
    ]
    
    # Add row colors based on status
    for i, row in enumerate(health_data[1:], 1):
        status_color = row[2]  # The color from get_health_status
        health_style.append(('BACKGROUND', (2, i), (2, i), status_color))
        health_style.append(('TEXTCOLOR', (2, i), (2, i), colors.white))
    
    health_table.setStyle(TableStyle(health_style))
    
    elements.append(health_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Recommendations section
    elements.append(Paragraph("Recommendations & Action Items", heading3_style))
    
    recommendations = []
    if len(blocked_issues) > 0:
        recommendations.append(f"• Address {len(blocked_issues)} blocked issue(s) to unblock development workflow")
    if len(unassigned_issues) > 5:
        recommendations.append(f"• Assign owners to {len(unassigned_issues)} unassigned issues for accountability")
    if len(high_priority_open) > 3:
        recommendations.append(f"• Prioritize resolution of {len(high_priority_open)} high-priority open issues")
    if len(stale_prs) > 0:
        recommendations.append(f"• Review and action {len(stale_prs)} stale pull request(s) to maintain momentum")
    if total_prs_opened > 0 and total_prs_merged / total_prs_opened < 0.5:
        recommendations.append(f"• Improve PR merge rate (currently {total_prs_merged/total_prs_opened*100:.0f}%) through faster reviews")
    
    if not recommendations:
        recommendations.append("• Project health metrics are within acceptable ranges. Continue current practices.")
    
    for rec in recommendations:
        elements.append(Paragraph(rec, body_style))
    
    elements.append(Spacer(1, 0.5*cm))
    
    # Footer
    elements.append(Spacer(1, 1*cm))
    footer_text = f"""<i>This automated report was generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')} 
    for {ORG_NAME}. Data encompasses Week {week_num} of {year} ({format_date(start)} through {format_date(end)}). 
    Report generated by GitHub Analytics System.</i>"""
    elements.append(Paragraph(footer_text, meta_style))
    
    # Build PDF
    doc.build(elements)
    print(f"✓ Professional PDF report generated: reports/{filename}")
    
    # Also update latest
    latest_path = reports_dir / 'latest.pdf'
    import shutil
    shutil.copy(str(filepath), str(latest_path))
    print(f"✓ Latest report updated: reports/latest.pdf")

def main():
    print("=" * 70)
    print("PROFESSIONAL WEEKLY PROGRESS REPORT GENERATOR")
    print("=" * 70)
    print(f"\nOrganization: {ORG_NAME}")
    print(f"Monitored Repositories: {', '.join([capitalize_repo_name(r) for r in REPOS])}\n")
    
    global start, end
    start, end = get_week_range()
    print(f"Reporting Period: {format_date(start)} to {format_date(end)}\n")
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