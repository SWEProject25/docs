#!/usr/bin/env python3

import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
import requests
from pathlib import Path

# Configuration
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
ORG_NAME = os.environ.get('ORG_NAME')
REPOS = ['frontend', 'backend', 'mobile', 'devops', 'testing']

if not GITHUB_TOKEN or not ORG_NAME:
    print("Error: GITHUB_TOKEN and ORG_NAME environment variables must be set")
    sys.exit(1)

HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

def get_week_range():
    """Get start and end dates for the past week"""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
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

def fetch_issues(repo, since):
    """Fetch all issues with complete details"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues'
    params = {'state': 'all', 'since': since.isoformat(), 'per_page': 100}
    issues = github_api_get(url, params)
    
    if not isinstance(issues, list):
        return []
    
    # Filter out PRs and enrich with timeline data
    enriched = []
    for issue in issues:
        if 'pull_request' in issue:
            continue
        
        # Fetch timeline for assignment and status changes
        timeline_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues/{issue["number"]}/timeline'
        issue['timeline'] = github_api_get(timeline_url)
        if not isinstance(issue['timeline'], list):
            issue['timeline'] = []
        
        enriched.append(issue)
    
    return enriched

def fetch_pull_requests(repo, since):
    """Fetch PRs for completion tracking"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls'
    params = {'state': 'all', 'sort': 'updated', 'direction': 'desc', 'per_page': 100}
    prs = github_api_get(url, params)
    
    if not isinstance(prs, list):
        return []
    
    filtered = []
    for pr in prs:
        try:
            updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
            if updated_at >= since:
                filtered.append(pr)
        except (KeyError, ValueError):
            continue
    
    return filtered

def fetch_milestones(repo):
    """Fetch milestones for sprint tracking"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/milestones'
    params = {'state': 'all', 'per_page': 100}
    milestones = github_api_get(url, params)
    return milestones if isinstance(milestones, list) else []

def categorize_issue(issue):
    """Determine issue type from labels"""
    labels = [label['name'].lower() for label in issue.get('labels', [])]
    title = issue.get('title', '').lower()
    
    type_keywords = {
        'bug': ['bug', 'fix', 'error', 'broken'],
        'feature': ['feature', 'enhancement', 'new'],
        'documentation': ['docs', 'documentation'],
        'task': ['task', 'chore'],
        'security': ['security', 'vulnerability'],
        'performance': ['performance', 'optimization']
    }
    
    for issue_type, keywords in type_keywords.items():
        if any(keyword in ' '.join(labels + [title]) for keyword in keywords):
            return issue_type
    
    return 'other'

def get_issue_priority(issue):
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

def extract_assignment_history(issue):
    """Extract who assigned the issue and when"""
    assignments = []
    for event in issue.get('timeline', []):
        if event.get('event') == 'assigned':
            assignments.append({
                'assignee': event.get('assignee', {}).get('login', 'unknown'),
                'assigner': event.get('assigner', {}).get('login', 'unknown'),
                'date': event.get('created_at', 'N/A')
            })
    return assignments

def calculate_completion_time(issue):
    """Calculate time from creation to closure"""
    if not issue.get('closed_at'):
        return None
    
    created = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
    closed = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
    delta = closed - created
    
    days = delta.days
    hours = delta.seconds // 3600
    
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours}h"

def generate_sprint_report(all_data, week_range):
    """Generate comprehensive sprint documentation"""
    start, end = week_range
    week_num = end.isocalendar()[1]
    year = end.year
    
    md = [
        f"# Sprint Report - Week {week_num}, {year}\n\n",
        f"**Organization:** {ORG_NAME}\n",
        f"**Period:** {format_date(start)} to {format_date(end)}\n",
        f"**Generated:** {format_date(end)}\n\n",
        "---\n\n"
    ]
    
    # Executive Summary
    total_issues_created = sum(len(repo['issues']) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at')]) for repo in all_data)
    total_issues_open = total_issues_created - total_issues_closed
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at')]) for repo in all_data)
    
    md.extend([
        "## Sprint Overview\n\n",
        f"- Issues Created: **{total_issues_created}**\n",
        f"- Issues Closed: **{total_issues_closed}**\n",
        f"- Issues Still Open: **{total_issues_open}**\n",
        f"- Pull Requests Merged: **{total_prs_merged}**\n",
        f"- Active Repositories: **{len([r for r in all_data if len(r['issues']) > 0])}/{len(REPOS)}**\n\n",
        "---\n\n"
    ])
    
    # Repository Details
    for repo_data in all_data:
        repo_name = repo_data['name']
        issues = repo_data['issues']
        prs = repo_data['pull_requests']
        milestones = repo_data['milestones']
        
        if not issues and not prs:
            continue
        
        md.append(f"## Repository: {repo_name}\n\n")
        
        # Milestone Progress
        if milestones:
            md.append("### Sprint Milestones\n\n")
            for milestone in milestones:
                total = milestone.get('open_issues', 0) + milestone.get('closed_issues', 0)
                closed = milestone.get('closed_issues', 0)
                progress = (closed / total * 100) if total > 0 else 0
                status = "Closed" if milestone['state'] == 'closed' else "Active"
                
                md.append(f"**{milestone['title']}** ({status})\n")
                md.append(f"- Progress: {closed}/{total} issues ({progress:.0f}%)\n")
                if milestone.get('due_on'):
                    md.append(f"- Due Date: {milestone['due_on'][:10]}\n")
                md.append("\n")
        
        # Issues Breakdown
        if issues:
            md.append("### Issues Activity\n\n")
            
            open_issues = [i for i in issues if i['state'] == 'open']
            closed_issues = [i for i in issues if i['state'] == 'closed']
            
            md.append(f"**Status:** {len(open_issues)} Open | {len(closed_issues)} Closed\n\n")
            
            # Type breakdown
            type_counts = Counter([categorize_issue(i) for i in issues])
            md.append("**By Type:**\n")
            for issue_type, count in type_counts.most_common():
                md.append(f"- {issue_type.capitalize()}: {count}\n")
            md.append("\n")
            
            # Priority breakdown
            priority_counts = Counter([get_issue_priority(i) for i in issues])
            md.append("**By Priority:**\n")
            for priority, count in sorted(priority_counts.items(), key=lambda x: {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}.get(x[0], 4)):
                md.append(f"- {priority}: {count}\n")
            md.append("\n")
            
            # Detailed issue list
            md.append("### Issue Details\n\n")
            
            for issue in sorted(issues, key=lambda x: x['number']):
                status = "Open" if issue['state'] == 'open' else "Closed"
                issue_type = categorize_issue(issue)
                priority = get_issue_priority(issue)
                
                md.append(f"#### #{issue['number']} - {issue['title']}\n\n")
                md.append(f"**Link:** {issue['html_url']}\n\n")
                md.append(f"**Details:**\n")
                md.append(f"- Status: {status}\n")
                md.append(f"- Type: {issue_type.capitalize()}\n")
                md.append(f"- Priority: {priority}\n")
                md.append(f"- Created: {issue['created_at'][:10]} by {issue.get('user', {}).get('login', 'unknown')}\n")
                
                if issue.get('closed_at'):
                    completion_time = calculate_completion_time(issue)
                    md.append(f"- Closed: {issue['closed_at'][:10]} (took {completion_time})\n")
                
                # Labels
                if issue.get('labels'):
                    labels_str = ', '.join([f"`{l['name']}`" for l in issue['labels']])
                    md.append(f"- Labels: {labels_str}\n")
                
                # Assignees
                if issue.get('assignees'):
                    assignees_str = ', '.join([a['login'] for a in issue['assignees']])
                    md.append(f"- Assigned To: {assignees_str}\n")
                
                # Assignment history
                assignments = extract_assignment_history(issue)
                if assignments:
                    md.append(f"- Assignment History:\n")
                    for assignment in assignments:
                        md.append(f"  - {assignment['assigner']} assigned to {assignment['assignee']} on {assignment['date'][:10]}\n")
                
                # Milestone
                if issue.get('milestone'):
                    md.append(f"- Milestone: {issue['milestone']['title']}\n")
                
                md.append("\n")
        
        # Pull Requests Summary
        if prs:
            md.append("### Pull Requests\n\n")
            
            merged = [pr for pr in prs if pr.get('merged_at')]
            open_prs = [pr for pr in prs if pr['state'] == 'open']
            
            md.append(f"**Status:** {len(open_prs)} Open | {len(merged)} Merged\n\n")
            
            for pr in prs[:10]:
                status = "Merged" if pr.get('merged_at') else ("Open" if pr['state'] == 'open' else "Closed")
                md.append(f"- **#{pr['number']}** - {pr['title']}\n")
                md.append(f"  - Status: {status}\n")
                md.append(f"  - Author: {pr.get('user', {}).get('login', 'unknown')}\n")
                md.append(f"  - Changes: +{pr.get('additions', 0)}/-{pr.get('deletions', 0)} lines\n")
                md.append(f"  - Link: {pr['html_url']}\n\n")
        
        md.append("---\n\n")
    
    # Team Analytics
    md.append("## Team Analytics\n\n")
    
    # Collect all issues and PRs
    all_issues = [issue for repo in all_data for issue in repo['issues']]
    all_prs = [pr for repo in all_data for pr in repo['pull_requests']]
    
    # Team member contributions
    team_stats = defaultdict(lambda: {
        'issues_created': 0,
        'issues_closed': 0,
        'prs_opened': 0,
        'prs_merged': 0,
        'issues_assigned': 0,
        'repos': set()
    })
    
    for repo_data in all_data:
        repo_name = repo_data['name']
        
        for issue in repo_data['issues']:
            creator = issue.get('user', {}).get('login', 'unknown')
            team_stats[creator]['issues_created'] += 1
            team_stats[creator]['repos'].add(repo_name)
            
            if issue.get('closed_at'):
                if issue.get('closed_by'):
                    closer = issue['closed_by'].get('login', 'unknown')
                    team_stats[closer]['issues_closed'] += 1
                    team_stats[closer]['repos'].add(repo_name)
            
            for assignee in issue.get('assignees', []):
                assignee_name = assignee['login']
                team_stats[assignee_name]['issues_assigned'] += 1
                team_stats[assignee_name]['repos'].add(repo_name)
        
        for pr in repo_data['pull_requests']:
            author = pr.get('user', {}).get('login', 'unknown')
            team_stats[author]['prs_opened'] += 1
            team_stats[author]['repos'].add(repo_name)
            
            if pr.get('merged_at'):
                team_stats[author]['prs_merged'] += 1
    
    md.append("### Team Member Contributions\n\n")
    md.append("| Member | Issues Created | Issues Closed | Issues Assigned | PRs Opened | PRs Merged | Repositories |\n")
    md.append("|--------|----------------|---------------|-----------------|------------|------------|-------------|\n")
    
    sorted_team = sorted(
        team_stats.items(),
        key=lambda x: x[1]['issues_created'] + x[1]['prs_opened'],
        reverse=True
    )
    
    for member, stats in sorted_team:
        repos_str = ', '.join(sorted(stats['repos']))
        md.append(
            f"| {member} | {stats['issues_created']} | {stats['issues_closed']} | "
            f"{stats['issues_assigned']} | {stats['prs_opened']} | {stats['prs_merged']} | {repos_str} |\n"
        )
    
    md.append("\n")
    
    # Sprint Velocity
    md.append("### Sprint Velocity\n\n")
    closed_this_week = total_issues_closed
    merged_this_week = total_prs_merged
    velocity_score = closed_this_week + merged_this_week
    
    md.append(f"- Issues Closed: **{closed_this_week}**\n")
    md.append(f"- PRs Merged: **{merged_this_week}**\n")
    md.append(f"- Velocity Score: **{velocity_score}**\n\n")
    
    # Outstanding work
    md.append("### Outstanding Work\n\n")
    
    all_open = [i for i in all_issues if i['state'] == 'open']
    blocked = [i for i in all_open if any('block' in l['name'].lower() or 'waiting' in l['name'].lower() for l in i.get('labels', []))]
    unassigned = [i for i in all_open if not i.get('assignees')]
    
    md.append(f"- Total Open Issues: **{len(all_open)}**\n")
    if blocked:
        md.append(f"- Blocked Issues: **{len(blocked)}** (requires attention)\n")
    if unassigned:
        md.append(f"- Unassigned Issues: **{len(unassigned)}**\n")
    
    md.append("\n---\n\n")
    md.append(f"*Report generated on {format_date(end)}*\n")
    
    return ''.join(md)

def main():
    print("Starting sprint report generation...")
    print(f"Organization: {ORG_NAME}")
    print(f"Repositories: {', '.join(REPOS)}\n")
    
    start, end = get_week_range()
    print(f"Period: {format_date(start)} to {format_date(end)}\n")
    
    all_data = []
    
    for repo in REPOS:
        print(f"Processing {repo}...")
        
        issues = fetch_issues(repo, start)
        pull_requests = fetch_pull_requests(repo, start)
        milestones = fetch_milestones(repo)
        
        print(f"  - {len(issues)} issues")
        print(f"  - {len(pull_requests)} pull requests")
        print(f"  - {len(milestones)} milestones\n")
        
        all_data.append({
            'name': repo,
            'issues': issues,
            'pull_requests': pull_requests,
            'milestones': milestones
        })
    
    print("Generating sprint report...")
    markdown = generate_sprint_report(all_data, (start, end))
    
    # Save report
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    week_num = end.isocalendar()[1]
    year = end.year
    filename = f"sprint_week_{week_num}_{year}.md"
    filepath = reports_dir / filename
    
    filepath.write_text(markdown, encoding='utf-8')
    print(f"Report saved: sprint_reports/{filename}")
    
    # Update latest
    latest_path = reports_dir / 'latest.md'
    latest_path.write_text(markdown, encoding='utf-8')
    print(f"Latest updated: sprint_reports/latest.md")
    
    print("\nSprint report generation complete!")

if __name__ == '__main__':
    main()