#!/usr/bin/env python3
"""
Weekly Progress Report Generator for Social Network Project
Extracts data from GitHub Projects and generates formatted reports
"""

import os
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_OWNER = os.getenv('REPO_OWNER')
REPO_NAME = os.getenv('REPO_NAME')
WEEK_NUMBER = os.getenv('WEEK_NUMBER', 'auto')

REPOSITORIES = ["frontend", "backend", "mobile", "testing", "devops"]

HEADERS = {
    'Authorization': f'Bearer {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
}

def get_week_number():
    """Calculate current week number or use manual input"""
    if WEEK_NUMBER != 'auto':
        return WEEK_NUMBER
    
    # Calculate week number from project start - UPDATE THIS DATE
    project_start = datetime(2025, 1, 1)  # Change to your actual project start date
    current = datetime.now()
    weeks = (current - project_start).days // 7 + 1
    return f"Week-{weeks}"

def get_repository_contributors():
    """Fetch all contributors from the repository"""
    url = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contributors'
    
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code != 200:
        print(f"⚠️  Warning: Could not fetch contributors: {response.status_code}")
        return []
    
    contributors = response.json()
    usernames = [contrib['login'] for contrib in contributors]
    print(f"✅ Found {len(usernames)} contributors in repository")
    return usernames

def get_commits_this_week(repo_name):
    """Get commits from the last 7 days for a repo"""
    since = (datetime.now() - timedelta(days=7)).isoformat()
    url = f'https://api.github.com/repos/{REPO_OWNER}/{repo_name}/commits'
    params = {'since': since, 'per_page': 100}
    
    all_commits = []
    page = 1
    
    while True:
        params['page'] = page
        response = requests.get(url, headers=HEADERS, params=params)
        
        if response.status_code != 200:
            print(f"⚠️  Warning: Could not fetch commits for {repo_name}: {response.status_code}")
            break
        
        commits = response.json()
        if not commits:
            break
            
        # tag commits with repo name
        for commit in commits:
            commit["__repo"] = repo_name
        
        all_commits.extend(commits)
        page += 1
        
        if len(all_commits) >= 500:
            break
    
    print(f"✅ {repo_name}: {len(all_commits)} commits this week")
    return all_commits


def get_pull_requests_this_week():
    """Get pull requests from the last 7 days"""
    since = (datetime.now() - timedelta(days=7)).isoformat()
    url = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls'
    params = {'state': 'all', 'sort': 'updated', 'per_page': 100}
    
    response = requests.get(url, headers=HEADERS, params=params)
    
    if response.status_code != 200:
        print(f"⚠️  Warning: Could not fetch pull requests: {response.status_code}")
        return []
    
    all_prs = response.json()
    
    # Filter PRs updated in the last 7 days
    week_ago = datetime.now() - timedelta(days=7)
    recent_prs = []
    
    for pr in all_prs:
        updated = datetime.strptime(pr['updated_at'], '%Y-%m-%dT%H:%M:%SZ')
        if updated >= week_ago:
            recent_prs.append(pr)
    
    print(f"✅ Found {len(recent_prs)} pull requests this week")
    return recent_prs

def get_issues_this_week():
    """Get issues created or updated in the last 7 days"""
    since = (datetime.now() - timedelta(days=7)).isoformat()
    url = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues'
    params = {'state': 'all', 'since': since, 'per_page': 100}
    
    response = requests.get(url, headers=HEADERS, params=params)
    
    if response.status_code != 200:
        print(f"⚠️  Warning: Could not fetch issues: {response.status_code}")
        return []
    
    # Filter out pull requests (they appear as issues in the API)
    issues = [issue for issue in response.json() if 'pull_request' not in issue]
    
    print(f"✅ Found {len(issues)} issues this week")
    return issues

def organize_data_by_member(commits, pull_requests, issues):
    """Organize all activity by team member"""
    member_data = defaultdict(lambda: {
        'commits': [],
        'pull_requests_created': [],
        'pull_requests_merged': [],
        'pull_requests_reviewed': [],
        'issues_created': [],
        'issues_closed': [],
        'lines_added': 0,
        'lines_deleted': 0
    })
    
    # Process commits
    for commit in commits:
        author = commit.get('author')
        if author and author.get('login'):
            username = author['login']
            
            commit_data = commit.get('commit', {})
            stats = commit.get('stats', {})
            
            member_data[username]['commits'].append({
                'message': commit_data.get('message', '').split('\n')[0],
                'sha': commit['sha'][:7],
                'date': commit_data.get('author', {}).get('date', ''),
                'additions': stats.get('additions', 0),
                'deletions': stats.get('deletions', 0)
            })
            
            member_data[username]['lines_added'] += stats.get('additions', 0)
            member_data[username]['lines_deleted'] += stats.get('deletions', 0)
    
    # Process pull requests
    for pr in pull_requests:
        user = pr.get('user', {}).get('login')
        if user:
            pr_data = {
                'number': pr['number'],
                'title': pr['title'],
                'state': pr['state'],
                'created_at': pr['created_at'],
                'merged_at': pr.get('merged_at'),
                'additions': pr.get('additions', 0),
                'deletions': pr.get('deletions', 0)
            }
            
            member_data[user]['pull_requests_created'].append(pr_data)
            
            if pr.get('merged_at'):
                member_data[user]['pull_requests_merged'].append(pr_data)
    
    # Process issues
    for issue in issues:
        user = issue.get('user', {}).get('login')
        if user:
            issue_data = {
                'number': issue['number'],
                'title': issue['title'],
                'state': issue['state'],
                'created_at': issue['created_at'],
                'closed_at': issue.get('closed_at')
            }
            
            member_data[user]['issues_created'].append(issue_data)
            
            if issue.get('state') == 'closed' and issue.get('closed_at'):
                closed_date = datetime.strptime(issue['closed_at'], '%Y-%m-%dT%H:%M:%SZ')
                week_ago = datetime.now() - timedelta(days=7)
                if closed_date >= week_ago:
                    member_data[user]['issues_closed'].append(issue_data)
    
    return dict(member_data)

def calculate_stats(member_data):
    """Calculate statistics for each member"""
    stats = {}
    
    for member, data in member_data.items():
        stats[member] = {
            'commits': len(data['commits']),
            'prs_created': len(data['pull_requests_created']),
            'prs_merged': len(data['pull_requests_merged']),
            'issues_created': len(data['issues_created']),
            'issues_closed': len(data['issues_closed']),
            'lines_added': data['lines_added'],
            'lines_deleted': data['lines_deleted'],
            'total_activity': (len(data['commits']) + len(data['pull_requests_created']) + 
                             len(data['issues_created']) + len(data['issues_closed']))
        }
    
    return stats

def generate_markdown_report(week, member_data, stats):
    """Generate formatted markdown report"""
    total_commits = sum(s['commits'] for s in stats.values())
    total_prs = sum(s['prs_created'] for s in stats.values())
    total_issues = sum(s['issues_created'] for s in stats.values())
    total_lines_added = sum(s['lines_added'] for s in stats.values())
    total_lines_deleted = sum(s['lines_deleted'] for s in stats.values())
    
    report = f"""# 📊 Weekly Progress Report - {week}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Project:** Social Network (Twitter Clone)  
**Period:** Last 7 days

---

## 🎯 Summary

- **Total Team Members Active:** {len(member_data)}
- **Total Commits:** {total_commits}
- **Pull Requests Created:** {total_prs}
- **Issues Created:** {total_issues}
- **Lines Added:** {total_lines_added:,}
- **Lines Deleted:** {total_lines_deleted:,}
- **Net Lines Changed:** {(total_lines_added - total_lines_deleted):,}

---

## 📊 Team Overview

| Member | Commits | PRs Created | PRs Merged | Issues Created | Issues Closed | Lines +/- | Activity Score |
|--------|---------|-------------|------------|----------------|---------------|-----------|----------------|
"""
    
    # Sort by total activity (most active first)
    sorted_members = sorted(stats.items(), key=lambda x: x[1]['total_activity'], reverse=True)
    
    for member, stat in sorted_members:
        lines_change = f"+{stat['lines_added']}/{-stat['lines_deleted']}"
        activity_bar = '⭐' * min(stat['total_activity'], 10)
        
        report += f"| {member} | {stat['commits']} | {stat['prs_created']} | {stat['prs_merged']} | {stat['issues_created']} | {stat['issues_closed']} | {lines_change} | {activity_bar} {stat['total_activity']} |\n"
    
    report += "\n---\n\n"
    
    # Individual member details
    for member, data in sorted(member_data.items()):
        stat = stats[member]
        
        report += f"""## 👤 {member}

**Activity Summary:**
- Commits: {stat['commits']}
- Pull Requests: {stat['prs_created']} created, {stat['prs_merged']} merged
- Issues: {stat['issues_created']} created, {stat['issues_closed']} closed
- Code Changes: +{stat['lines_added']:,} / -{stat['lines_deleted']:,} lines

"""
        
        # Commits section
        if data['commits']:
            report += f"### 💻 Commits ({len(data['commits'])})\n"
            for commit in data['commits'][:15]:  # Show max 15
                report += f"- `{commit['sha']}` {commit['message']}\n"
            if len(data['commits']) > 15:
                report += f"- *...and {len(data['commits']) - 15} more commits*\n"
        
        # Pull Requests section
        if data['pull_requests_created']:
            report += f"\n### 🔀 Pull Requests ({len(data['pull_requests_created'])})\n"
            for pr in data['pull_requests_created']:
                status = "✅ Merged" if pr['merged_at'] else f"📝 {pr['state'].title()}"
                report += f"- #{pr['number']}: {pr['title']} ({status})\n"
        
        # Issues section
        if data['issues_created']:
            report += f"\n### 📋 Issues ({len(data['issues_created'])})\n"
            for issue in data['issues_created']:
                status = "✅ Closed" if issue['state'] == 'closed' else "📝 Open"
                report += f"- #{issue['number']}: {issue['title']} ({status})\n"
        
        if not data['commits'] and not data['pull_requests_created'] and not data['issues_created']:
            report += "*No activity this week*\n"
        
        report += "\n---\n\n"
    
    # Add recommendations section
    report += """## 📌 Notes

- Activity score is calculated based on commits, PRs, and issues
- Only activity from the last 7 days is included
- Pull requests and issues are counted when created or updated this week

## 🎯 Next Steps

Review individual contributions and ensure all team members are making progress on their assigned modules.

"""
    
    return report

def save_report(week, report):
    """Save report to file"""
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    week_dir = reports_dir / week
    week_dir.mkdir(exist_ok=True)
    
    # Save main report
    report_file = week_dir / 'progress_report.md'
    report_file.write_text(report)
    
    print(f"✅ Report saved to: {report_file}")
    
    # Update index
    update_index(reports_dir, week)

def update_index(reports_dir, latest_week):
    """Update the main index file"""
    index_file = reports_dir / 'README.md'
    
    # Get all week directories
    weeks = sorted([d.name for d in reports_dir.iterdir() if d.is_dir()], reverse=True)
    
    index_content = f"""# Progress Reports Index

**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 📅 Available Reports

"""
    
    for week in weeks:
        report_file = reports_dir / week / 'progress_report.md'
        if report_file.exists():
            index_content += f"- [{week}](./{week}/progress_report.md)\n"
    
    index_file.write_text(index_content)

def main():
    print("🚀 Starting Weekly Report Generation...")
    print(f"📦 Repository: {REPO_OWNER}/{REPO_NAME}")
    
    week = get_week_number()
    print(f"📅 Generating report for: {week}\n")
    
    # Fetch all data
    print("📡 Fetching data from GitHub...")
    contributors = get_repository_contributors()
    commits = get_commits_this_week()
    pull_requests = get_pull_requests_this_week()
    issues = get_issues_this_week()
    
    # Process data
    print("\n⚙️  Processing data...")
    member_data = organize_data_by_member(commits, pull_requests, issues)
    stats = calculate_stats(member_data)
    
    # Generate report
    print("📝 Generating report...")
    report = generate_markdown_report(week, member_data, stats)
    
    # Save report
    save_report(week, report)
    
    print(f"\n✅ Report generation complete!")
    print(f"📊 Team members with activity: {len(member_data)}")
    print(f"💻 Total commits: {sum(s['commits'] for s in stats.values())}")
    print(f"🔀 Total PRs: {sum(s['prs_created'] for s in stats.values())}")
    print(f"📋 Total issues: {sum(s['issues_created'] for s in stats.values())}")

if __name__ == '__main__':
    main()