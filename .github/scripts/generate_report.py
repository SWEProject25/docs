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

if not GITHUB_TOKEN or not ORG_NAME:
    print("❌ Error: GITHUB_TOKEN and ORG_NAME environment variables must be set")
    sys.exit(1)

HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

def get_week_range():
    """Get start and end dates for the past week (timezone-aware)"""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    return start, end

def get_week_number(date):
    """Get ISO week number"""
    return date.isocalendar()[1]

def format_date(date):
    """Format date as YYYY-MM-DD"""
    return date.strftime('%Y-%m-%d')

def format_datetime(date):
    """Format datetime as YYYY-MM-DD HH:MM UTC"""
    return date.strftime('%Y-%m-%d %H:%M UTC')

def github_api_get(url, params=None):
    """Make GET request to GitHub API"""
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  API Error for {url}: {e}")
        return []

def fetch_commits(repo, since, until):
    """Fetch commits for a repository with detailed information"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/commits'
    params = {
        'since': since.isoformat(),
        'until': until.isoformat(),
        'per_page': 100
    }
    print(f"  📝 Fetching commits...")
    commits = github_api_get(url, params)
    return commits if isinstance(commits, list) else []

def fetch_pull_requests(repo, since):
    """Fetch pull requests for a repository"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls'
    params = {
        'state': 'all',
        'sort': 'updated',
        'direction': 'desc',
        'per_page': 100
    }
    print(f"  🔀 Fetching pull requests...")
    prs = github_api_get(url, params)
    
    if not isinstance(prs, list):
        return []
    
    # Filter PRs updated within the time range
    filtered_prs = []
    for pr in prs:
        try:
            updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
            if updated_at >= since:
                filtered_prs.append(pr)
        except (KeyError, ValueError) as e:
            print(f"⚠️  Error parsing PR date: {e}")
            continue
    
    return filtered_prs

def fetch_issues(repo, since):
    """Fetch issues for a repository"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues'
    params = {
        'state': 'all',
        'since': since.isoformat(),
        'per_page': 100
    }
    print(f"  🎫 Fetching issues...")
    issues = github_api_get(url, params)
    
    if not isinstance(issues, list):
        return []
    
    # Filter out pull requests (they appear in issues API too)
    filtered_issues = [issue for issue in issues if 'pull_request' not in issue]
    return filtered_issues

def fetch_projects(repo):
    """Fetch GitHub Projects (Kanban) data - handles deprecated API gracefully"""
    # Note: Classic Projects API is deprecated, but we'll try it
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/projects'
    params = {'per_page': 10}
    
    print(f"  📊 Fetching project boards...")
    projects = github_api_get(url, params)
    
    if not isinstance(projects, list):
        return []
    
    projects_data = []
    
    for project in projects:
        # Fetch columns for this project
        columns_url = f"https://api.github.com/projects/{project['id']}/columns"
        columns = github_api_get(columns_url)
        
        if not isinstance(columns, list):
            continue
        
        columns_data = []
        for column in columns:
            # Fetch cards for this column
            cards_url = f"https://api.github.com/projects/columns/{column['id']}/cards"
            cards = github_api_get(cards_url)
            
            card_count = len(cards) if isinstance(cards, list) else 0
            columns_data.append({
                'name': column['name'],
                'card_count': card_count
            })
        
        projects_data.append({
            'name': project['name'],
            'columns': columns_data
        })
    
    return projects_data

def aggregate_detailed_contributors(commits, pull_requests, issues, repo_name):
    """Aggregate detailed contribution statistics by contributor"""
    contributors = defaultdict(lambda: {
        'commits': [],
        'prs_created': [],
        'prs_merged': [],
        'prs_reviewed': [],
        'issues_created': [],
        'issues_closed': [],
        'total_additions': 0,
        'total_deletions': 0,
        'repos': set()
    })
    
    # Process commits
    for commit in commits:
        if commit and 'commit' in commit and 'author' in commit['commit']:
            author_name = commit['commit']['author']['name']
            author_email = commit['commit']['author'].get('email', 'unknown')
            
            commit_data = {
                'sha': commit['sha'][:7],
                'message': commit['commit']['message'].split('\n')[0][:80],
                'date': commit['commit']['author'].get('date', 'unknown'),
                'url': commit.get('html_url', '')
            }
            
            # Get commit stats if available
            if 'stats' in commit:
                contributors[author_name]['total_additions'] += commit['stats'].get('additions', 0)
                contributors[author_name]['total_deletions'] += commit['stats'].get('deletions', 0)
            
            contributors[author_name]['commits'].append(commit_data)
            contributors[author_name]['repos'].add(repo_name)
    
    # Process pull requests
    for pr in pull_requests:
        # PR Creator
        if pr.get('user'):
            creator = pr['user'].get('login', 'unknown')
            pr_data = {
                'number': pr['number'],
                'title': pr['title'],
                'state': pr['state'],
                'url': pr['html_url'],
                'created_at': pr.get('created_at', 'unknown'),
                'merged_at': pr.get('merged_at')
            }
            
            contributors[creator]['prs_created'].append(pr_data)
            contributors[creator]['repos'].add(repo_name)
            
            # Track merged PRs
            if pr.get('merged_at'):
                contributors[creator]['prs_merged'].append(pr_data)
    
    # Process issues
    for issue in issues:
        if issue.get('user'):
            creator = issue['user'].get('login', 'unknown')
            issue_data = {
                'number': issue['number'],
                'title': issue['title'],
                'state': issue['state'],
                'url': issue['html_url'],
                'created_at': issue.get('created_at', 'unknown')
            }
            
            contributors[creator]['issues_created'].append(issue_data)
            contributors[creator]['repos'].add(repo_name)
            
            # Track closed issues
            if issue.get('closed_at'):
                contributors[creator]['issues_closed'].append(issue_data)
    
    return dict(contributors)

def generate_markdown(all_data, week_range):
    """Generate comprehensive production-level markdown report"""
    start, end = week_range
    week_num = get_week_number(end)
    year = end.year
    
    md = [
        f"# 📊 Weekly Engineering Progress Report\n\n",
        f"**Organization:** `{ORG_NAME}`  \n",
        f"**Report Period:** Week {week_num}, {year}  \n",
        f"**Date Range:** {format_date(start)} to {format_date(end)}  \n",
        f"**Generated:** {format_datetime(end)}  \n",
        "\n---\n\n"
    ]
    
    # Executive Summary
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_prs = sum(len(repo['pull_requests']) for repo in all_data)
    total_issues = sum(len(repo['issues']) for repo in all_data)
    merged_prs = sum(
        len([pr for pr in repo['pull_requests'] if pr.get('merged_at')])
        for repo in all_data
    )
    closed_issues = sum(
        len([issue for issue in repo['issues'] if issue.get('closed_at')])
        for repo in all_data
    )
    active_repos = len([repo for repo in all_data if len(repo['commits']) > 0])
    
    # Calculate total code changes
    total_additions = 0
    total_deletions = 0
    for repo_data in all_data:
        for commit in repo_data['commits']:
            if 'stats' in commit:
                total_additions += commit['stats'].get('additions', 0)
                total_deletions += commit['stats'].get('deletions', 0)
    
    md.extend([
        "## 📈 Executive Summary\n\n",
        "| Metric | Count |\n",
        "|--------|-------|\n",
        f"| Total Commits | {total_commits} |\n",
        f"| Code Additions | +{total_additions:,} lines |\n",
        f"| Code Deletions | -{total_deletions:,} lines |\n",
        f"| Pull Requests (Total) | {total_prs} |\n",
        f"| Pull Requests (Merged) | {merged_prs} |\n",
        f"| Issues (Total) | {total_issues} |\n",
        f"| Issues (Closed) | {closed_issues} |\n",
        f"| Active Repositories | {active_repos}/{len(REPOS)} |\n\n"
    ])
    
    # Repository-Level Detailed Breakdown
    md.append("## 🗂️ Repository-Level Analysis\n\n")
    
    for repo_data in all_data:
        repo_name = repo_data['name']
        md.append(f"### 📦 {repo_name.capitalize()}\n\n")
        
        # Repository Stats
        commits_count = len(repo_data['commits'])
        prs_count = len(repo_data['pull_requests'])
        merged_count = len([pr for pr in repo_data['pull_requests'] if pr.get('merged_at')])
        issues_created = len(repo_data['issues'])
        issues_closed = len([i for i in repo_data['issues'] if i.get('closed_at')])
        
        # Calculate repo-specific code changes
        repo_additions = sum(c['stats'].get('additions', 0) for c in repo_data['commits'] if 'stats' in c)
        repo_deletions = sum(c['stats'].get('deletions', 0) for c in repo_data['commits'] if 'stats' in c)
        
        md.extend([
            "**📊 Activity Metrics:**\n\n",
            "| Metric | Value |\n",
            "|--------|-------|\n",
            f"| Commits | {commits_count} |\n",
            f"| Lines Added | +{repo_additions:,} |\n",
            f"| Lines Removed | -{repo_deletions:,} |\n",
            f"| Pull Requests | {prs_count} ({merged_count} merged) |\n",
            f"| Issues | {issues_created} created, {issues_closed} closed |\n\n"
        ])
        
        # Detailed Commit Log
        if repo_data['commits']:
            md.append("**📝 Commit History:**\n\n")
            for commit in repo_data['commits'][:10]:  # Show up to 10 commits
                if commit and 'commit' in commit:
                    sha = commit['sha'][:7]
                    message = commit['commit']['message'].split('\n')[0][:100]
                    author = commit['commit']['author']['name']
                    date = commit['commit']['author'].get('date', 'unknown')
                    url = commit.get('html_url', '#')
                    
                    md.append(f"- [`{sha}`]({url}) - {message}  \n")
                    md.append(f"  *by {author} on {date[:10]}*\n\n")
            
            if len(repo_data['commits']) > 10:
                md.append(f"*...and {len(repo_data['commits']) - 10} more commits*\n\n")
        
        # Pull Requests Detail
        if repo_data['pull_requests']:
            md.append("**🔀 Pull Requests:**\n\n")
            for pr in repo_data['pull_requests'][:10]:
                status_icon = "✅" if pr.get('merged_at') else ("🔄" if pr['state'] == 'open' else "❌")
                status_text = "Merged" if pr.get('merged_at') else pr['state'].capitalize()
                creator = pr.get('user', {}).get('login', 'unknown')
                
                md.append(f"- {status_icon} **[PR #{pr['number']}]({pr['html_url']})** - {pr['title']}  \n")
                md.append(f"  *{status_text} by @{creator}*\n\n")
            
            if len(repo_data['pull_requests']) > 10:
                md.append(f"*...and {len(repo_data['pull_requests']) - 10} more PRs*\n\n")
        
        # Issues Detail
        if repo_data['issues']:
            md.append("**🎫 Issues:**\n\n")
            for issue in repo_data['issues'][:10]:
                status_icon = "✅" if issue.get('closed_at') else "🔄"
                status_text = "Closed" if issue.get('closed_at') else "Open"
                creator = issue.get('user', {}).get('login', 'unknown')
                
                md.append(f"- {status_icon} **[Issue #{issue['number']}]({issue['html_url']})** - {issue['title']}  \n")
                md.append(f"  *{status_text} by @{creator}*\n\n")
            
            if len(repo_data['issues']) > 10:
                md.append(f"*...and {len(repo_data['issues']) - 10} more issues*\n\n")
        
        # Project Boards
        if repo_data['projects']:
            md.append("**📊 Project Board Status:**\n\n")
            for project in repo_data['projects']:
                md.append(f"- **{project['name']}**\n")
                for column in project['columns']:
                    md.append(f"  - {column['name']}: {column['card_count']} cards\n")
                md.append("\n")
        
        md.append("---\n\n")
    
    # Comprehensive Team Contributions
    md.append("## 👥 Detailed Team Contributions\n\n")
    
    all_contributors = defaultdict(lambda: {
        'commits': 0,
        'prs_created': 0,
        'prs_merged': 0,
        'issues_created': 0,
        'issues_closed': 0,
        'repos': set(),
        'additions': 0,
        'deletions': 0
    })
    
    detailed_activities = defaultdict(lambda: defaultdict(list))
    
    for repo_data in all_data:
        repo_contributors = aggregate_detailed_contributors(
            repo_data['commits'],
            repo_data['pull_requests'],
            repo_data['issues'],
            repo_data['name']
        )
        
        for name, stats in repo_contributors.items():
            all_contributors[name]['commits'] += len(stats['commits'])
            all_contributors[name]['prs_created'] += len(stats['prs_created'])
            all_contributors[name]['prs_merged'] += len(stats['prs_merged'])
            all_contributors[name]['issues_created'] += len(stats['issues_created'])
            all_contributors[name]['issues_closed'] += len(stats['issues_closed'])
            all_contributors[name]['repos'].update(stats['repos'])
            all_contributors[name]['additions'] += stats['total_additions']
            all_contributors[name]['deletions'] += stats['total_deletions']
            
            # Store detailed activities
            detailed_activities[name][repo_data['name']].extend(stats['commits'])
    
    # Summary Table
    sorted_contributors = sorted(
        all_contributors.items(),
        key=lambda x: x[1]['commits'],
        reverse=True
    )
    
    if sorted_contributors:
        md.append("### 📊 Contribution Summary\n\n")
        md.append("| Contributor | Commits | PRs Created | PRs Merged | Issues Created | Issues Closed | Code Changes | Repos |\n")
        md.append("|-------------|---------|-------------|------------|----------------|---------------|--------------|-------|\n")
        
        for name, stats in sorted_contributors:
            repos_str = ', '.join(sorted(stats['repos']))
            code_changes = f"+{stats['additions']:,}/-{stats['deletions']:,}"
            md.append(
                f"| {name} | {stats['commits']} | {stats['prs_created']} | "
                f"{stats['prs_merged']} | {stats['issues_created']} | "
                f"{stats['issues_closed']} | {code_changes} | {repos_str} |\n"
            )
        md.append("\n")
    
    # Detailed Individual Contributions
    md.append("### 📝 Individual Activity Details\n\n")
    
    for name, stats in sorted_contributors:
        if stats['commits'] == 0:
            continue
            
        md.append(f"#### 👤 {name}\n\n")
        md.append(f"**Overview:** {stats['commits']} commits across {len(stats['repos'])} repositories\n\n")
        
        # Show commits by repository
        for repo_name in sorted(stats['repos']):
            repo_commits = detailed_activities[name].get(repo_name, [])
            if repo_commits:
                md.append(f"**{repo_name.capitalize()}** ({len(repo_commits)} commits):\n\n")
                for commit in repo_commits[:5]:  # Show up to 5 commits per repo
                    md.append(f"- [`{commit['sha']}`]({commit['url']}) {commit['message']}  \n")
                    md.append(f"  *{commit['date'][:10]}*\n\n")
                
                if len(repo_commits) > 5:
                    md.append(f"*...and {len(repo_commits) - 5} more commits*\n\n")
        
        md.append("\n")
    
    # Key Achievements
    md.append("## 🎯 Key Achievements & Highlights\n\n")
    achievements = []
    
    if merged_prs > 0:
        achievements.append(f"✅ Successfully merged {merged_prs} pull request{'s' if merged_prs != 1 else ''}")
    if closed_issues > 0:
        achievements.append(f"🎫 Resolved {closed_issues} issue{'s' if closed_issues != 1 else ''}")
    if total_commits > 50:
        achievements.append(f"🚀 High development velocity with {total_commits} commits")
    if total_additions > 1000:
        achievements.append(f"💻 Significant codebase expansion: +{total_additions:,} lines added")
    if active_repos == len(REPOS):
        achievements.append(f"🏆 All {len(REPOS)} repositories actively maintained")
    
    if achievements:
        for achievement in achievements:
            md.append(f"- {achievement}\n")
    else:
        md.append("- 📋 Maintenance week - focus on planning and documentation\n")
    
    # Footer
    md.extend([
        "\n---\n\n",
        f"*📄 This report was automatically generated on {format_datetime(end)}*  \n",
        f"*🤖 Report Generator: GitHub Actions Workflow*  \n",
        f"*📊 Data Source: GitHub REST API v3*\n"
    ])
    
    return ''.join(md)

def main():
    print("🚀 Starting weekly report generation...")
    print(f"📦 Organization: {ORG_NAME}")
    
    start, end = get_week_range()
    print(f"📅 Date range: {format_date(start)} to {format_date(end)}\n")
    
    all_data = []
    
    for repo in REPOS:
        print(f"📦 Processing {repo}...")
        
        commits = fetch_commits(repo, start, end)
        pull_requests = fetch_pull_requests(repo, start)
        issues = fetch_issues(repo, start)
        projects = fetch_projects(repo)
        
        print(f"  ✓ {len(commits)} commits")
        print(f"  ✓ {len(pull_requests)} PRs")
        print(f"  ✓ {len(issues)} issues")
        print(f"  ✓ {len(projects)} projects\n")
        
        all_data.append({
            'name': repo,
            'commits': commits,
            'pull_requests': pull_requests,
            'issues': issues,
            'projects': projects
        })
    
    # Generate markdown
    print("📝 Generating production-level markdown report...")
    markdown = generate_markdown(all_data, (start, end))
    
    # Save report
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    week_num = get_week_number(end)
    year = end.year
    filename = f"week-{week_num}-{year}.md"
    filepath = reports_dir / filename
    
    filepath.write_text(markdown, encoding='utf-8')
    print(f"✅ Report saved to: reports/{filename}")
    print(f"📊 Report size: {len(markdown):,} characters")
    
    # Also update latest report
    latest_path = reports_dir / 'latest.md'
    latest_path.write_text(markdown, encoding='utf-8')
    print(f"✅ Latest report updated: reports/latest.md")
    
    print("\n🎉 Report generation complete!")

if __name__ == '__main__':
    main()