#!/usr/bin/env python3

import os
import sys
from datetime import datetime, timedelta
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
    """Get start and end dates for the past week"""
    end = datetime.now()
    start = end - timedelta(days=7)
    return start, end

def get_week_number(date):
    """Get ISO week number"""
    return date.isocalendar()[1]

def format_date(date):
    """Format date as YYYY-MM-DD"""
    return date.strftime('%Y-%m-%d')

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
    """Fetch commits for a repository"""
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
    filtered_prs = [
        pr for pr in prs 
        if datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00')) >= since
    ]
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
    """Fetch GitHub Projects (Kanban) data for a repository"""
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

def aggregate_contributors(commits):
    """Aggregate commit statistics by contributor"""
    contributors = defaultdict(lambda: {'commits': 0})
    
    for commit in commits:
        if commit and 'commit' in commit and 'author' in commit['commit']:
            author = commit['commit']['author']['name']
            contributors[author]['commits'] += 1
    
    return dict(contributors)

def generate_markdown(all_data, week_range):
    """Generate markdown report"""
    start, end = week_range
    week_num = get_week_number(end)
    year = end.year
    
    md = [
        f"# 📊 Weekly Progress Report\n",
        f"**Week {week_num}, {year}** | {format_date(start)} to {format_date(end)}\n",
        "---\n"
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
    
    md.extend([
        "## 📈 Executive Summary\n",
        f"- **Total Commits**: {total_commits}\n",
        f"- **Pull Requests**: {total_prs} ({merged_prs} merged)\n",
        f"- **Issues**: {total_issues} ({closed_issues} closed)\n",
        f"- **Active Repositories**: {active_repos}/{len(REPOS)}\n"
    ])
    
    # Per-Repository Breakdown
    md.append("\n## 🗂️ Repository Breakdown\n")
    
    for repo_data in all_data:
        repo_name = repo_data['name']
        md.append(f"\n### {repo_name.capitalize()}\n")
        
        # Stats
        commits_count = len(repo_data['commits'])
        prs_count = len(repo_data['pull_requests'])
        merged_count = len([pr for pr in repo_data['pull_requests'] if pr.get('merged_at')])
        issues_created = len([i for i in repo_data['issues'] if i.get('created_at')])
        issues_closed = len([i for i in repo_data['issues'] if i.get('closed_at')])
        
        md.extend([
            "**Activity Summary:**\n",
            f"- Commits: {commits_count}\n",
            f"- Pull Requests: {prs_count} ({merged_count} merged)\n",
            f"- Issues: {issues_created} created, {issues_closed} closed\n"
        ])
        
        # Projects/Kanban
        if repo_data['projects']:
            md.append("\n**Project Boards:**\n")
            for project in repo_data['projects']:
                md.append(f"- **{project['name']}**\n")
                for column in project['columns']:
                    md.append(f"  - {column['name']}: {column['card_count']} cards\n")
        
        # Notable PRs
        notable_prs = [
            pr for pr in repo_data['pull_requests']
            if pr.get('merged_at') or pr.get('state') == 'open'
        ][:5]
        
        if notable_prs:
            md.append("\n**Notable Pull Requests:**\n")
            for pr in notable_prs:
                if pr.get('merged_at'):
                    status = "✅ Merged"
                elif pr.get('state') == 'open':
                    status = "🔄 Open"
                else:
                    status = "❌ Closed"
                md.append(f"- {status}: [#{pr['number']}]({pr['html_url']}) - {pr['title']}\n")
        
        # Top Contributors
        contributors = aggregate_contributors(repo_data['commits'])
        top_contributors = sorted(
            contributors.items(),
            key=lambda x: x[1]['commits'],
            reverse=True
        )[:3]
        
        if top_contributors:
            md.append("\n**Top Contributors:**\n")
            for name, stats in top_contributors:
                md.append(f"- {name}: {stats['commits']} commits\n")
        
        md.append("\n---\n")
    
    # Overall Team Contributions
    md.append("\n## 👥 Team Contributions\n")
    
    all_contributors = defaultdict(lambda: {'commits': 0, 'repos': set()})
    for repo_data in all_data:
        repo_contributors = aggregate_contributors(repo_data['commits'])
        for name, stats in repo_contributors.items():
            all_contributors[name]['commits'] += stats['commits']
            all_contributors[name]['repos'].add(repo_data['name'])
    
    sorted_contributors = sorted(
        all_contributors.items(),
        key=lambda x: x[1]['commits'],
        reverse=True
    )
    
    if sorted_contributors:
        md.append("\n| Contributor | Total Commits | Active Repos |\n")
        md.append("|-------------|---------------|---------------|\n")
        for name, stats in sorted_contributors:
            repos_str = ', '.join(sorted(stats['repos']))
            md.append(f"| {name} | {stats['commits']} | {repos_str} |\n")
    
    # Key Achievements
    md.append("\n## 🎯 Key Achievements\n")
    achievements = []
    
    if merged_prs > 0:
        achievements.append(f"✅ {merged_prs} pull requests merged successfully")
    if closed_issues > 0:
        achievements.append(f"🎫 {closed_issues} issues resolved")
    if total_commits > 50:
        achievements.append(f"🚀 High development velocity with {total_commits} commits")
    
    if achievements:
        for achievement in achievements:
            md.append(f"- {achievement}\n")
    else:
        md.append("- Maintenance week - focus on planning and documentation\n")
    
    # Footer
    md.extend([
        "\n---\n",
        f"*Report generated automatically on {format_date(end)}*\n"
    ])
    
    return ''.join(md)

def main():
    print("🚀 Starting weekly report generation...")
    
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
    print("📝 Generating markdown report...")
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
    
    # Also update latest report
    latest_path = reports_dir / 'latest.md'
    latest_path.write_text(markdown, encoding='utf-8')
    print(f"✅ Latest report updated: reports/latest.md")

if __name__ == '__main__':
    main()