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
    
    # Fetch commits
    commits_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/commits'
    commits_params = {'since': start.isoformat(), 'until': end.isoformat(), 'per_page': 100}
    commits = github_api_get(commits_url, commits_params)
    if not isinstance(commits, list):
        commits = []
    
    # Fetch issues (created or updated)
    issues_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues'
    issues_params = {'state': 'all', 'since': start.isoformat(), 'per_page': 100}
    all_issues = github_api_get(issues_url, issues_params)
    if not isinstance(all_issues, list):
        all_issues = []
    
    # Separate issues and PRs, filter by activity in date range
    issues = []
    for item in all_issues:
        if 'pull_request' in item:
            continue
        
        created = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
        updated = datetime.fromisoformat(item['updated_at'].replace('Z', '+00:00'))
        closed = datetime.fromisoformat(item['closed_at'].replace('Z', '+00:00')) if item.get('closed_at') else None
        
        # Check if any activity happened in our date range
        if created >= start or updated >= start or (closed and closed >= start):
            issues.append(item)
    
    # Fetch pull requests
    prs_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls'
    prs_params = {'state': 'all', 'sort': 'updated', 'direction': 'desc', 'per_page': 100}
    all_prs = github_api_get(prs_url, prs_params)
    if not isinstance(all_prs, list):
        all_prs = []
    
    # Filter PRs by activity in date range
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
        'bug': ['bug', 'fix', 'error', 'defect'],
        'feature': ['feature', 'enhancement', 'new'],
        'documentation': ['docs', 'documentation'],
        'task': ['task', 'chore'],
        'security': ['security', 'vulnerability'],
        'performance': ['performance', 'optimization', 'perf']
    }
    
    for issue_type, keywords in type_keywords.items():
        if any(keyword in label for label in labels for keyword in keywords):
            return issue_type.capitalize()
    
    return 'Task'

def get_priority(issue):
    """Extract priority from labels"""
    labels = [label['name'].lower() for label in issue.get('labels', [])]
    
    for label in labels:
        if 'critical' in label or 'p0' in label:
            return '🔴 Critical'
        if 'high' in label or 'p1' in label:
            return '🟠 High'
        if 'medium' in label or 'p2' in label:
            return '🟡 Medium'
        if 'low' in label or 'p3' in label:
            return '🟢 Low'
    
    return '⚪ Unset'

def get_labels_str(item):
    """Get formatted labels string"""
    labels = [label['name'] for label in item.get('labels', [])]
    if not labels:
        return '-'
    return ', '.join([f"`{label}`" for label in labels[:3]])

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

def generate_report(all_data, week_range):
    """Generate comprehensive weekly report"""
    start, end = week_range
    week_num = end.isocalendar()[1]
    year = end.year
    
    md = [
        f"# 📊 Weekly Progress Report - Week {week_num}, {year}\n\n",
        f"**Organization:** `{ORG_NAME}`  \n",
        f"**Reporting Period:** {format_date(start)} to {format_date(end)}  \n",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  \n\n",
        "---\n\n"
    ]
    
    # Calculate overall totals
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_issues_created = sum(len([i for i in repo['issues'] if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_opened = sum(len([pr for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    
    # Executive Summary
    md.extend([
        "## 📈 Executive Summary\n\n",
        "| Metric | Count |\n",
        "|--------|-------|\n",
        f"| Total Commits | {total_commits} |\n",
        f"| Issues Created | {total_issues_created} |\n",
        f"| Issues Closed | {total_issues_closed} |\n",
        f"| Pull Requests Opened | {total_prs_opened} |\n",
        f"| Pull Requests Merged | {total_prs_merged} |\n",
        f"| Active Repositories | {len([r for r in all_data if len(r['commits']) > 0 or len(r['issues']) > 0 or len(r['pull_requests']) > 0])}/{len(REPOS)} |\n\n",
        "---\n\n"
    ])
    
    # Repository Details
    md.append("## 📦 Repository Activity\n\n")
    
    for repo_data in all_data:
        repo_name = repo_data['name']
        commits = repo_data['commits']
        issues = repo_data['issues']
        prs = repo_data['pull_requests']
        
        # Categorize activity
        issues_created = [i for i in issues if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]
        issues_closed = [i for i in issues if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]
        issues_updated = [i for i in issues if i['state'] == 'open' and i not in issues_created]
        prs_opened = [pr for pr in prs if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]
        prs_merged = [pr for pr in prs if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]
        prs_closed = [pr for pr in prs if not pr.get('merged_at') and pr.get('closed_at') and datetime.fromisoformat(pr['closed_at'].replace('Z', '+00:00')) >= start]
        
        md.append(f"### 🔹 `{repo_name}`\n\n")
        
        # Check if there was any activity
        has_activity = len(commits) > 0 or len(issues_created) > 0 or len(issues_closed) > 0 or len(issues_updated) > 0 or len(prs_opened) > 0 or len(prs_merged) > 0
        
        if not has_activity:
            md.append("```\n⚠️  No activity recorded for this week.\n```\n\n")
            md.append("---\n\n")
            continue
        
        # Quick Stats
        md.append("**Weekly Statistics:**\n\n")
        md.append("| Metric | Count |\n")
        md.append("|--------|-------|\n")
        md.append(f"| Commits | {len(commits)} |\n")
        md.append(f"| Issues Created | {len(issues_created)} |\n")
        md.append(f"| Issues Closed | {len(issues_closed)} |\n")
        md.append(f"| Issues Updated | {len(issues_updated)} |\n")
        md.append(f"| PRs Opened | {len(prs_opened)} |\n")
        md.append(f"| PRs Merged | {len(prs_merged)} |\n")
        md.append(f"| PRs Closed (Unmerged) | {len(prs_closed)} |\n\n")
        
        # Commits section with grouped view
        if commits:
            md.append("#### 💻 Commits\n\n")
            commits_by_author = defaultdict(list)
            for commit in commits:
                author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
                commits_by_author[author].append(commit)
            
            md.append("| Author | Commits | Sample Messages |\n")
            md.append("|--------|---------|----------------|\n")
            
            for author, author_commits in sorted(commits_by_author.items(), key=lambda x: len(x[1]), reverse=True):
                sample_msgs = []
                for commit in author_commits[:3]:
                    msg = commit.get('commit', {}).get('message', '').split('\n')[0][:50]
                    sha = commit.get('sha', '')[:7]
                    url = commit.get('html_url', '')
                    sample_msgs.append(f"[`{sha}`]({url}) {msg}")
                
                msgs_str = '<br>'.join(sample_msgs)
                if len(author_commits) > 3:
                    msgs_str += f"<br>_...and {len(author_commits) - 3} more_"
                
                md.append(f"| {author} | {len(author_commits)} | {msgs_str} |\n")
            
            md.append("\n")
        
        # Issues Created Table
        if issues_created:
            md.append("#### 📝 Issues Created\n\n")
            md.append("| # | Title | Type | Priority | Labels | Creator | Assignee(s) | Status | Created |\n")
            md.append("|---|-------|------|----------|--------|---------|-------------|--------|----------|\n")
            
            for issue in sorted(issues_created, key=lambda x: x['number'], reverse=True):
                issue_num = f"[#{issue['number']}]({issue['html_url']})"
                title = issue['title'][:60] + ('...' if len(issue['title']) > 60 else '')
                issue_type = get_issue_type(issue)
                priority = get_priority(issue)
                labels = get_labels_str(issue)
                creator = issue.get('user', {}).get('login', 'N/A')
                assignees = ', '.join([a['login'] for a in issue.get('assignees', [])][:2]) or 'Unassigned'
                if len(issue.get('assignees', [])) > 2:
                    assignees += f" +{len(issue.get('assignees', [])) - 2}"
                status = '🟢 Open' if issue['state'] == 'open' else '✅ Closed'
                created_date = issue['created_at'][:10]
                
                md.append(f"| {issue_num} | {title} | {issue_type} | {priority} | {labels} | {creator} | {assignees} | {status} | {created_date} |\n")
            
            md.append("\n")
        
        # Issues Closed Table
        if issues_closed:
            md.append("#### ✅ Issues Closed\n\n")
            md.append("| # | Title | Type | Labels | Closed By | Time to Close | Closed Date |\n")
            md.append("|---|-------|------|--------|-----------|---------------|-------------|\n")
            
            for issue in sorted(issues_closed, key=lambda x: x['number'], reverse=True):
                issue_num = f"[#{issue['number']}]({issue['html_url']})"
                title = issue['title'][:60] + ('...' if len(issue['title']) > 60 else '')
                issue_type = get_issue_type(issue)
                labels = get_labels_str(issue)
                closed_by = issue.get('closed_by', {}).get('login', 'N/A') if issue.get('closed_by') else 'N/A'
                time_to_close = calculate_time_to_close(issue)
                closed_date = issue['closed_at'][:10] if issue.get('closed_at') else '-'
                
                md.append(f"| {issue_num} | {title} | {issue_type} | {labels} | {closed_by} | {time_to_close} | {closed_date} |\n")
            
            md.append("\n")
        
        # Issues Updated (Open)
        if issues_updated:
            md.append("#### 🔄 Issues Updated (Still Open)\n\n")
            md.append("| # | Title | Type | Priority | Labels | Assignee(s) | Last Updated |\n")
            md.append("|---|-------|------|----------|--------|-------------|---------------|\n")
            
            for issue in sorted(issues_updated, key=lambda x: x['updated_at'], reverse=True)[:10]:
                issue_num = f"[#{issue['number']}]({issue['html_url']})"
                title = issue['title'][:60] + ('...' if len(issue['title']) > 60 else '')
                issue_type = get_issue_type(issue)
                priority = get_priority(issue)
                labels = get_labels_str(issue)
                assignees = ', '.join([a['login'] for a in issue.get('assignees', [])][:2]) or 'Unassigned'
                if len(issue.get('assignees', [])) > 2:
                    assignees += f" +{len(issue.get('assignees', [])) - 2}"
                updated_date = issue['updated_at'][:10]
                
                md.append(f"| {issue_num} | {title} | {issue_type} | {priority} | {labels} | {assignees} | {updated_date} |\n")
            
            if len(issues_updated) > 10:
                md.append(f"\n_...and {len(issues_updated) - 10} more updated issues._\n")
            md.append("\n")
        
        # Pull Requests Opened Table
        if prs_opened:
            md.append("#### 🔀 Pull Requests Opened\n\n")
            md.append("| # | Title | Author | Status | Labels | Changes | Reviewers | Created |\n")
            md.append("|---|-------|--------|--------|--------|---------|-----------|----------|\n")
            
            for pr in sorted(prs_opened, key=lambda x: x['number'], reverse=True):
                pr_num = f"[#{pr['number']}]({pr['html_url']})"
                title = pr['title'][:50] + ('...' if len(pr['title']) > 50 else '')
                author = pr.get('user', {}).get('login', 'N/A')
                
                if pr.get('merged_at'):
                    status = '✅ Merged'
                elif pr['state'] == 'open':
                    status = '🟢 Open'
                else:
                    status = '❌ Closed'
                
                labels = get_labels_str(pr)
                changes = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                
                # Get reviewers
                reviewers = []
                if pr.get('requested_reviewers'):
                    reviewers = [r['login'] for r in pr['requested_reviewers'][:2]]
                reviewers_str = ', '.join(reviewers) if reviewers else '-'
                if len(pr.get('requested_reviewers', [])) > 2:
                    reviewers_str += f" +{len(pr.get('requested_reviewers', [])) - 2}"
                
                created_date = pr['created_at'][:10]
                
                md.append(f"| {pr_num} | {title} | {author} | {status} | {labels} | {changes} | {reviewers_str} | {created_date} |\n")
            
            md.append("\n")
        
        # Pull Requests Merged Table
        if prs_merged:
            md.append("#### ✅ Pull Requests Merged\n\n")
            md.append("| # | Title | Author | Merged By | Changes | Labels | Merged Date |\n")
            md.append("|---|-------|--------|-----------|---------|--------|-------------|\n")
            
            for pr in sorted(prs_merged, key=lambda x: x['merged_at'] if x.get('merged_at') else '', reverse=True):
                pr_num = f"[#{pr['number']}]({pr['html_url']})"
                title = pr['title'][:50] + ('...' if len(pr['title']) > 50 else '')
                author = pr.get('user', {}).get('login', 'N/A')
                merged_by = pr.get('merged_by', {}).get('login', 'N/A') if pr.get('merged_by') else 'N/A'
                changes = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                labels = get_labels_str(pr)
                merged_date = pr['merged_at'][:10] if pr.get('merged_at') else '-'
                
                md.append(f"| {pr_num} | {title} | {author} | {merged_by} | {changes} | {labels} | {merged_date} |\n")
            
            md.append("\n")
        
        md.append("---\n\n")
    
    # Team Contributions
    md.append("## 👥 Team Contributions\n\n")
    
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
            team_stats[author]['repos'].add(repo_name)
        
        for issue in repo_data['issues']:
            if datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00')) >= start:
                creator = issue.get('user', {}).get('login', 'unknown')
                team_stats[creator]['issues_created'] += 1
                team_stats[creator]['repos'].add(repo_name)
            
            if issue.get('closed_at') and datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00')) >= start:
                if issue.get('closed_by'):
                    closer = issue['closed_by'].get('login', 'unknown')
                    team_stats[closer]['issues_closed'] += 1
                    team_stats[closer]['repos'].add(repo_name)
        
        for pr in repo_data['pull_requests']:
            if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start:
                author = pr.get('user', {}).get('login', 'unknown')
                team_stats[author]['prs_opened'] += 1
                team_stats[author]['lines_added'] += pr.get('additions', 0)
                team_stats[author]['lines_deleted'] += pr.get('deletions', 0)
                team_stats[author]['repos'].add(repo_name)
            
            if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start:
                merger = pr.get('merged_by', {}).get('login', 'unknown') if pr.get('merged_by') else pr.get('user', {}).get('login', 'unknown')
                team_stats[merger]['prs_merged'] += 1
                team_stats[merger]['repos'].add(repo_name)
    
    md.append("| Member | Commits | Issues Created | Issues Closed | PRs Opened | PRs Merged | Code Changes | Active Repos |\n")
    md.append("|--------|---------|----------------|---------------|------------|------------|--------------|-------------|\n")
    
    sorted_team = sorted(
        team_stats.items(),
        key=lambda x: x[1]['commits'] + x[1]['prs_opened'] + x[1]['issues_created'],
        reverse=True
    )
    
    for member, stats in sorted_team:
        if stats['commits'] == 0 and stats['issues_created'] == 0 and stats['prs_opened'] == 0:
            continue
        
        repos_str = ', '.join(sorted(stats['repos'])) if stats['repos'] else '-'
        code_changes = f"+{stats['lines_added']}/-{stats['lines_deleted']}" if stats['lines_added'] > 0 or stats['lines_deleted'] > 0 else '-'
        
        md.append(
            f"| {member} | {stats['commits']} | {stats['issues_created']} | "
            f"{stats['issues_closed']} | {stats['prs_opened']} | {stats['prs_merged']} | {code_changes} | {repos_str} |\n"
        )
    
    md.append("\n")
    
    # Sprint Health Indicators
    md.append("## 🎯 Sprint Health Indicators\n\n")
    
    all_open_issues = [i for repo in all_data for i in repo['issues'] if i['state'] == 'open']
    blocked_issues = [i for i in all_open_issues if any('block' in l['name'].lower() or 'waiting' in l['name'].lower() for l in i.get('labels', []))]
    unassigned_issues = [i for i in all_open_issues if not i.get('assignees')]
    high_priority_open = [i for i in all_open_issues if any('critical' in l['name'].lower() or 'high' in l['name'].lower() or 'p0' in l['name'].lower() or 'p1' in l['name'].lower() for l in i.get('labels', []))]
    
    open_prs = [pr for repo in all_data for pr in repo['pull_requests'] if pr['state'] == 'open']
    stale_prs = [pr for pr in open_prs if (datetime.now(timezone.utc) - datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))).days > 7]
    
    md.append("| Indicator | Count | Status |\n")
    md.append("|-----------|-------|--------|\n")
    md.append(f"| Open Issues | {len(all_open_issues)} | {'⚠️ Review Needed' if len(all_open_issues) > 20 else '✅ Healthy'} |\n")
    md.append(f"| Blocked Issues | {len(blocked_issues)} | {'🔴 Critical' if len(blocked_issues) > 0 else '✅ None'} |\n")
    md.append(f"| Unassigned Issues | {len(unassigned_issues)} | {'⚠️ Needs Assignment' if len(unassigned_issues) > 5 else '✅ Acceptable'} |\n")
    md.append(f"| High Priority Open | {len(high_priority_open)} | {'🔴 Attention Required' if len(high_priority_open) > 3 else '✅ Under Control'} |\n")
    md.append(f"| Open Pull Requests | {len(open_prs)} | {'⚠️ Review Backlog' if len(open_prs) > 10 else '✅ Healthy'} |\n")
    md.append(f"| Stale PRs (>7 days) | {len(stale_prs)} | {'⚠️ Review ASAP' if len(stale_prs) > 0 else '✅ None'} |\n")
    
    md.append("\n---\n\n")
    
    # Footer
    md.append(f"<sub>Report generated automatically on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | ")
    md.append(f"Organization: {ORG_NAME} | Week {week_num}, {year}</sub>\n")
    
    return ''.join(md)

def main():
    print("=" * 60)
    print("Weekly Progress Report Generator")
    print("=" * 60)
    print(f"\nOrganization: {ORG_NAME}")
    print(f"Repositories: {', '.join(REPOS)}\n")
    
    global start, end
    start, end = get_week_range()
    print(f"Period: {format_date(start)} to {format_date(end)}\n")
    print("=" * 60)
    
    all_data = []
    
    for repo in REPOS:
        print(f"\n📦 Processing {repo}...")
        activity = fetch_repo_activity(repo, start, end)
        
        all_data.append({
            'name': repo,
            'commits': activity['commits'],
            'issues': activity['issues'],
            'pull_requests': activity['pull_requests']
        })
    
    print("\n" + "=" * 60)
    print("Generating comprehensive report...")
    markdown = generate_report(all_data, (start, end))
    
    # Save report
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    week_num = end.isocalendar()[1]
    year = end.year
    filename = f"week_{week_num}_{year}.md"
    filepath = reports_dir / filename
    
    filepath.write_text(markdown, encoding='utf-8')
    print(f"✅ Report saved: reports/{filename}")
    
    # Update latest
    latest_path = reports_dir / 'latest.md'
    latest_path.write_text(markdown, encoding='utf-8')
    print(f"✅ Latest updated: reports/latest.md")
    
    print("\n" + "=" * 60)
    print("✨ Weekly report generation complete!")
    print("=" * 60)

if __name__ == '__main__':
    main()