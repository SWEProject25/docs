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

def categorize_issues(issues):
    """Categorize issues by created, closed, updated"""
    return {
        'created': [i for i in issues if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start],
        'closed': [i for i in issues if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start],
        'updated': [i for i in issues if i['state'] == 'open']
    }

def categorize_prs(prs):
    """Categorize PRs by opened, merged, closed"""
    return {
        'opened': [pr for pr in prs if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start],
        'merged': [pr for pr in prs if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start],
        'closed': [pr for pr in prs if not pr.get('merged_at') and pr.get('closed_at') and datetime.fromisoformat(pr['closed_at'].replace('Z', '+00:00')) >= start]
    }

def generate_report(all_data, week_range):
    """Generate comprehensive weekly report"""
    start, end = week_range
    week_num = end.isocalendar()[1]
    year = end.year
    
    md = [
        f"# Weekly Report - Week {week_num}, {year}\n\n",
        f"**Organization:** {ORG_NAME}\n",
        f"**Period:** {format_date(start)} to {format_date(end)}\n",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n",
        "---\n\n"
    ]
    
    # Calculate overall totals
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_issues_created = sum(len([i for i in repo['issues'] if datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at') and datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_opened = sum(len([pr for pr in repo['pull_requests'] if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]) for repo in all_data)
    
    # Overall Summary
    md.extend([
        "## 📊 Overall Summary\n\n",
        f"- **Commits:** {total_commits}\n",
        f"- **Issues Created:** {total_issues_created}\n",
        f"- **Issues Closed:** {total_issues_closed}\n",
        f"- **PRs Opened:** {total_prs_opened}\n",
        f"- **PRs Merged:** {total_prs_merged}\n\n",
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
        prs_opened = [pr for pr in prs if datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= start]
        prs_merged = [pr for pr in prs if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start]
        
        md.append(f"### `{repo_name}`\n\n")
        
        # Check if there was any activity
        has_activity = len(commits) > 0 or len(issues_created) > 0 or len(issues_closed) > 0 or len(prs_opened) > 0 or len(prs_merged) > 0
        
        if not has_activity:
            md.append("_No activity this week._\n\n")
            md.append("---\n\n")
            continue
        
        # Activity summary
        md.append("**Activity Summary:**\n")
        md.append(f"- Commits: {len(commits)}\n")
        md.append(f"- Issues: {len(issues_created)} created, {len(issues_closed)} closed\n")
        md.append(f"- Pull Requests: {len(prs_opened)} opened, {len(prs_merged)} merged\n\n")
        
        # Commits section
        if commits:
            md.append("#### Commits\n\n")
            # Group commits by author
            commits_by_author = defaultdict(list)
            for commit in commits[:20]:  # Limit to recent 20
                author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
                commits_by_author[author].append(commit)
            
            for author, author_commits in sorted(commits_by_author.items()):
                md.append(f"**{author}** ({len(author_commits)} commits)\n")
                for commit in author_commits[:5]:  # Show first 5 per author
                    msg = commit.get('commit', {}).get('message', '').split('\n')[0][:80]
                    sha = commit.get('sha', '')[:7]
                    url = commit.get('html_url', '')
                    md.append(f"- [`{sha}`]({url}) {msg}\n")
                if len(author_commits) > 5:
                    md.append(f"- _...and {len(author_commits) - 5} more_\n")
                md.append("\n")
        
        # Issues section
        if issues_created or issues_closed:
            md.append("#### Issues\n\n")
            
            if issues_created:
                md.append(f"**Created ({len(issues_created)}):**\n\n")
                for issue in issues_created[:10]:
                    md.append(f"- **#{issue['number']}** [{issue['title']}]({issue['html_url']})\n")
                    md.append(f"  - Created by: {issue.get('user', {}).get('login', 'unknown')}\n")
                if len(issues_created) > 10:
                    md.append(f"- _...and {len(issues_created) - 10} more_\n")
                md.append("\n")
            
            if issues_closed:
                md.append(f"**Closed ({len(issues_closed)}):**\n\n")
                for issue in issues_closed[:10]:
                    md.append(f"- **#{issue['number']}** [{issue['title']}]({issue['html_url']})\n")
                    closed_by = issue.get('closed_by', {}).get('login', 'unknown') if issue.get('closed_by') else 'unknown'
                    md.append(f"  - Closed by: {closed_by}\n")
                if len(issues_closed) > 10:
                    md.append(f"- _...and {len(issues_closed) - 10} more_\n")
                md.append("\n")
        
        # Pull Requests section
        if prs_opened or prs_merged:
            md.append("#### Pull Requests\n\n")
            
            if prs_opened:
                md.append(f"**Opened ({len(prs_opened)}):**\n\n")
                for pr in prs_opened[:10]:
                    status = "✅ Merged" if pr.get('merged_at') else ("🟢 Open" if pr['state'] == 'open' else "❌ Closed")
                    md.append(f"- **#{pr['number']}** [{pr['title']}]({pr['html_url']}) {status}\n")
                    md.append(f"  - Author: {pr.get('user', {}).get('login', 'unknown')}\n")
                    md.append(f"  - Changes: +{pr.get('additions', 0)}/-{pr.get('deletions', 0)} lines\n")
                if len(prs_opened) > 10:
                    md.append(f"- _...and {len(prs_opened) - 10} more_\n")
                md.append("\n")
            
            if prs_merged:
                md.append(f"**Merged ({len(prs_merged)}):**\n\n")
                for pr in prs_merged[:10]:
                    md.append(f"- **#{pr['number']}** [{pr['title']}]({pr['html_url']})\n")
                    md.append(f"  - Author: {pr.get('user', {}).get('login', 'unknown')}\n")
                    merged_by = pr.get('merged_by', {}).get('login', 'unknown') if pr.get('merged_by') else 'unknown'
                    md.append(f"  - Merged by: {merged_by}\n")
                if len(prs_merged) > 10:
                    md.append(f"- _...and {len(prs_merged) - 10} more_\n")
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
                team_stats[author]['repos'].add(repo_name)
            
            if pr.get('merged_at') and datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) >= start:
                merger = pr.get('merged_by', {}).get('login', 'unknown') if pr.get('merged_by') else pr.get('user', {}).get('login', 'unknown')
                team_stats[merger]['prs_merged'] += 1
                team_stats[merger]['repos'].add(repo_name)
    
    md.append("| Member | Commits | Issues Created | Issues Closed | PRs Opened | PRs Merged | Repositories |\n")
    md.append("|--------|---------|----------------|---------------|------------|------------|-------------|\n")
    
    sorted_team = sorted(
        team_stats.items(),
        key=lambda x: x[1]['commits'] + x[1]['prs_opened'] + x[1]['issues_created'],
        reverse=True
    )
    
    for member, stats in sorted_team:
        if stats['commits'] == 0 and stats['issues_created'] == 0 and stats['prs_opened'] == 0:
            continue
        repos_str = ', '.join(sorted(stats['repos'])) if stats['repos'] else '-'
        md.append(
            f"| {member} | {stats['commits']} | {stats['issues_created']} | "
            f"{stats['issues_closed']} | {stats['prs_opened']} | {stats['prs_merged']} | {repos_str} |\n"
        )
    
    md.append("\n---\n\n")
    md.append(f"*Report generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n")
    
    return ''.join(md)

def main():
    print("Starting weekly report generation...")
    print(f"Organization: {ORG_NAME}")
    print(f"Repositories: {', '.join(REPOS)}\n")
    
    global start, end
    start, end = get_week_range()
    print(f"Period: {format_date(start)} to {format_date(end)}\n")
    
    all_data = []
    
    for repo in REPOS:
        print(f"Processing {repo}...")
        activity = fetch_repo_activity(repo, start, end)
        
        all_data.append({
            'name': repo,
            'commits': activity['commits'],
            'issues': activity['issues'],
            'pull_requests': activity['pull_requests']
        })
    
    print("\nGenerating weekly report...")
    markdown = generate_report(all_data, (start, end))
    
    # Save report
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    week_num = end.isocalendar()[1]
    year = end.year
    filename = f"week_{week_num}_{year}.md"
    filepath = reports_dir / filename
    
    filepath.write_text(markdown, encoding='utf-8')
    print(f"Report saved: reports/{filename}")
    
    # Update latest
    latest_path = reports_dir / 'latest.md'
    latest_path.write_text(markdown, encoding='utf-8')
    print(f"Latest updated: reports/latest.md")
    
    print("\nWeekly report generation complete!")

if __name__ == '__main__':
    main()