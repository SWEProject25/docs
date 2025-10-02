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
        'Docs': ['docs', 'documentation'],
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
        return '-'
    
    created = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
    closed = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
    delta = closed - created
    
    days = delta.days
    hours = delta.seconds // 3600
    
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h"

def generate_pdf_report(all_data, week_range):
    """Generate professional PDF report"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, KeepTogether
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    
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
        rightMargin=40,
        leftMargin=40,
        topMargin=50,
        bottomMargin=40
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=16,
        fontName='Helvetica-Bold'
    )
    
    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=13,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    # Title Page
    elements.append(Spacer(1, 1.5*inch))
    elements.append(Paragraph(f"Weekly Progress Report", title_style))
    elements.append(Paragraph(f"Week {week_num}, {year}", title_style))
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph(f"Organization: {ORG_NAME}", subtitle_style))
    elements.append(Paragraph(f"Period: {format_date(start)} to {format_date(end)}", subtitle_style))
    elements.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", subtitle_style))
    
    elements.append(PageBreak())
    
    # Calculate totals
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_issues_created = sum(len([i for i in repo['issues'] if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_opened = sum(len([pr for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    
    # Executive Summary
    elements.append(Paragraph("Executive Summary", heading2_style))
    
    summary_data = [
        ['Metric', 'Count'],
        ['Total Commits', str(total_commits)],
        ['Issues Created', str(total_issues_created)],
        ['Issues Closed', str(total_issues_closed)],
        ['Pull Requests Opened', str(total_prs_opened)],
        ['Pull Requests Merged', str(total_prs_merged)],
        ['Active Repositories', f"{len([r for r in all_data if len(r['commits']) > 0 or len(r['issues']) > 0 or len(r['pull_requests']) > 0])}/{len(REPOS)}"]
    ]
    
    summary_table = Table(summary_data, colWidths=[3.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Repository Activity
    for repo_data in all_data:
        repo_name = repo_data['name']
        commits = repo_data['commits']
        issues = repo_data['issues']
        prs = repo_data['pull_requests']
        
        issues_created = [i for i in issues if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]
        issues_closed = [i for i in issues if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]
        prs_opened = [pr for pr in prs if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]
        prs_merged = [pr for pr in prs if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]
        
        has_activity = len(commits) > 0 or len(issues_created) > 0 or len(issues_closed) > 0 or len(prs_opened) > 0 or len(prs_merged) > 0
        
        elements.append(Paragraph(f"Repository: {repo_name}", heading2_style))
        
        if not has_activity:
            elements.append(Paragraph("No activity recorded for this week.", styles['Normal']))
            elements.append(Spacer(1, 0.2*inch))
            continue
        
        # Repo stats
        repo_stats_data = [
            ['Metric', 'Count'],
            ['Commits', str(len(commits))],
            ['Issues Created', str(len(issues_created))],
            ['Issues Closed', str(len(issues_closed))],
            ['PRs Opened', str(len(prs_opened))],
            ['PRs Merged', str(len(prs_merged))]
        ]
        
        repo_stats_table = Table(repo_stats_data, colWidths=[3.5*inch, 2*inch])
        repo_stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        
        elements.append(repo_stats_table)
        elements.append(Spacer(1, 0.15*inch))
        
        # Issues Created
        if issues_created:
            elements.append(Paragraph("Issues Created", heading3_style))
            
            issues_data = [['#', 'Title', 'Type', 'Priority', 'Creator', 'Status']]
            for issue in sorted(issues_created, key=lambda x: x['number'], reverse=True)[:10]:
                title = issue['title'][:40] + '...' if len(issue['title']) > 40 else issue['title']
                status = 'Open' if issue['state'] == 'open' else 'Closed'
                issues_data.append([
                    f"#{issue['number']}",
                    title,
                    get_issue_type(issue),
                    get_priority(issue),
                    issue.get('user', {}).get('login', 'N/A')[:15],
                    status
                ])
            
            issues_table = Table(issues_data, colWidths=[0.5*inch, 2.2*inch, 0.7*inch, 0.8*inch, 0.9*inch, 0.6*inch])
            issues_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(issues_table)
            elements.append(Spacer(1, 0.15*inch))
        
        # PRs Opened
        if prs_opened:
            elements.append(Paragraph("Pull Requests", heading3_style))
            
            prs_data = [['#', 'Title', 'Author', 'Status', 'Changes']]
            for pr in sorted(prs_opened, key=lambda x: x['number'], reverse=True)[:10]:
                title = pr['title'][:45] + '...' if len(pr['title']) > 45 else pr['title']
                if pr.get('merged_at'):
                    status = 'Merged'
                elif pr['state'] == 'open':
                    status = 'Open'
                else:
                    status = 'Closed'
                
                changes = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                
                prs_data.append([
                    f"#{pr['number']}",
                    title,
                    pr.get('user', {}).get('login', 'N/A')[:15],
                    status,
                    changes
                ])
            
            prs_table = Table(prs_data, colWidths=[0.5*inch, 2.5*inch, 1*inch, 0.7*inch, 1*inch])
            prs_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9b59b6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(prs_table)
            elements.append(Spacer(1, 0.2*inch))
    
    # Team Contributions (new page)
    elements.append(PageBreak())
    elements.append(Paragraph("Team Contributions", heading2_style))
    
    team_stats = defaultdict(lambda: {
        'commits': 0,
        'issues_created': 0,
        'issues_closed': 0,
        'prs_opened': 0,
        'prs_merged': 0
    })
    
    for repo_data in all_data:
        for commit in repo_data['commits']:
            author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
            team_stats[author]['commits'] += 1
        
        for issue in repo_data['issues']:
            if datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00')) >= start:
                creator = issue.get('user', {}).get('login', 'unknown')
                team_stats[creator]['issues_created'] += 1
            
            if issue.get('closed_at') and datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00')) >= start:
                if issue.get('closed_by'):
                    closer = issue['closed_by'].get('login', 'unknown')
                    team_stats[closer]['issues_closed'] += 1
        
        for pr in repo_data['pull_requests']:
            if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start:
                author = pr.get('user', {}).get('login', 'unknown')
                team_stats[author]['prs_opened'] += 1
            
            if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start:
                merger = pr.get('merged_by', {}).get('login', 'unknown') if pr.get('merged_by') else pr.get('user', {}).get('login', 'unknown')
                team_stats[merger]['prs_merged'] += 1
    
    team_data = [['Member', 'Commits', 'Issues Created', 'Issues Closed', 'PRs Opened', 'PRs Merged']]
    
    sorted_team = sorted(
        team_stats.items(),
        key=lambda x: x[1]['commits'] + x[1]['prs_opened'] + x[1]['issues_created'],
        reverse=True
    )
    
    for member, stats in sorted_team:
        if stats['commits'] == 0 and stats['issues_created'] == 0 and stats['prs_opened'] == 0:
            continue
        
        team_data.append([
            member[:20],
            str(stats['commits']),
            str(stats['issues_created']),
            str(stats['issues_closed']),
            str(stats['prs_opened']),
            str(stats['prs_merged'])
        ])
    
    team_table = Table(team_data, colWidths=[1.8*inch, 0.8*inch, 1*inch, 1*inch, 0.9*inch, 0.9*inch])
    team_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 7),
    ]))
    
    elements.append(team_table)
    
    # Build PDF
    doc.build(elements)
    print(f"PDF report saved: reports/{filename}")
    
    # Also update latest
    latest_path = reports_dir / 'latest.pdf'
    import shutil
    shutil.copy(str(filepath), str(latest_path))
    print(f"Latest updated: reports/latest.pdf")

def main():
    print("=" * 60)
    print("Weekly Progress Report Generator (PDF)")
    print("=" * 60)
    print(f"\nOrganization: {ORG_NAME}")
    print(f"Repositories: {', '.join(REPOS)}\n")
    
    global start, end
    start, end = get_week_range()
    print(f"Period: {format_date(start)} to {format_date(end)}\n")
    print("=" * 60)
    
    all_data = []
    
    for repo in REPOS:
        print(f"\nProcessing {repo}...")
        activity = fetch_repo_activity(repo, start, end)
        
        all_data.append({
            'name': repo,
            'commits': activity['commits'],
            'issues': activity['issues'],
            'pull_requests': activity['pull_requests']
        })
    
    print("\n" + "=" * 60)
    print("Generating PDF report...")
    generate_pdf_report(all_data, (start, end))
    
    print("\n" + "=" * 60)
    print("Weekly report generation complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()