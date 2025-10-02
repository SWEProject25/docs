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
    print("❌ Error: GITHUB_TOKEN and ORG_NAME environment variables must be set")
    sys.exit(1)

HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# ============================================================================
# FEATURE TOGGLES - Comment out any section you don't want in the report
# ============================================================================

FEATURES = {
    'commits': True,              # Commit history and code changes
    'pull_requests': True,        # PR tracking and reviews
    'issues': True,               # Issue tracking and management
    'issue_labels': True,         # Label analysis and categorization
    'issue_milestones': True,     # Milestone tracking
    'issue_assignees': True,      # Assignment tracking
    'issue_timeline': True,       # Issue event timeline
    'projects': True,             # Classic project boards (deprecated API)
    'projects_v2': True,          # New GitHub Projects (GraphQL)
    'languages': True,            # Programming language stats
    'contributors': True,         # Contributor statistics
    'code_frequency': True,       # Code frequency over time
    'commit_activity': True,      # Weekly commit activity
    'pr_reviews': True,           # Detailed PR review data
    'pr_comments': True,          # PR review comments
    'issue_comments': True,       # Issue discussion threads
    'reactions': True,            # Emoji reactions on issues/PRs
    'branch_protection': True,    # Branch protection rules
    'deployment': True,           # Deployment history
    'release_notes': True,        # Release tracking
    'workflow_runs': True,        # GitHub Actions runs
    'code_scanning': True,        # Security alerts
    'dependency_graph': True,     # Dependencies and vulnerabilities
    'traffic': True,              # Repository traffic stats
    'milestones_detail': True,    # Detailed milestone progress
    'team_velocity': True,        # Sprint velocity metrics
    'time_tracking': True,        # Issue resolution time
    'pr_cycle_time': True,        # PR lifecycle metrics
    'issue_types': True,          # Bug/Feature/Enhancement breakdown
    'priority_analysis': True,    # Priority level tracking
    'blocked_issues': True,       # Blocked/waiting status
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
    """Make GET request to GitHub API with error handling"""
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  API Error for {url}: {e}")
        return [] if "list" in url or "[]" in str(e) else {}

def github_graphql_query(query, variables=None):
    """Execute GraphQL query for Projects V2"""
    url = 'https://api.github.com/graphql'
    payload = {'query': query, 'variables': variables or {}}
    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"⚠️  GraphQL Error: {e}")
        return {}

# ============================================================================
# COMMIT DATA
# ============================================================================

def fetch_commits(repo, since, until):
    """Fetch commits with detailed stats"""
    if not FEATURES['commits']:
        return []
    
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/commits'
    params = {'since': since.isoformat(), 'until': until.isoformat(), 'per_page': 100}
    print(f"  📝 Fetching commits...")
    commits = github_api_get(url, params)
    
    detailed_commits = []
    for commit in (commits if isinstance(commits, list) else []):
        if commit.get('sha'):
            detail_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/commits/{commit["sha"]}'
            detailed_commit = github_api_get(detail_url)
            if detailed_commit:
                detailed_commits.append(detailed_commit)
    
    return detailed_commits

# ============================================================================
# PULL REQUEST DATA
# ============================================================================

def fetch_pull_requests(repo, since):
    """Fetch PRs with comprehensive details"""
    if not FEATURES['pull_requests']:
        return []
    
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls'
    params = {'state': 'all', 'sort': 'updated', 'direction': 'desc', 'per_page': 100}
    print(f"  🔀 Fetching pull requests...")
    prs = github_api_get(url, params)
    
    if not isinstance(prs, list):
        return []
    
    filtered_prs = []
    for pr in prs:
        try:
            updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
            if updated_at >= since:
                # Enrich PR with reviews and comments
                if FEATURES['pr_reviews']:
                    pr['review_data'] = fetch_pr_reviews(repo, pr['number'])
                if FEATURES['pr_comments']:
                    pr['comment_data'] = fetch_pr_comments(repo, pr['number'])
                if FEATURES['reactions']:
                    pr['reactions'] = fetch_reactions(repo, 'pulls', pr['number'])
                filtered_prs.append(pr)
        except (KeyError, ValueError):
            continue
    
    return filtered_prs

def fetch_pr_reviews(repo, pr_number):
    """Fetch PR reviews"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls/{pr_number}/reviews'
    reviews = github_api_get(url)
    return reviews if isinstance(reviews, list) else []

def fetch_pr_comments(repo, pr_number):
    """Fetch PR review comments"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/pulls/{pr_number}/comments'
    comments = github_api_get(url)
    return comments if isinstance(comments, list) else []

# ============================================================================
# ISSUE DATA (TICKETS/KANBAN)
# ============================================================================

def fetch_issues(repo, since):
    """Fetch issues with comprehensive ticket details"""
    if not FEATURES['issues']:
        return []
    
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues'
    params = {'state': 'all', 'since': since.isoformat(), 'per_page': 100}
    print(f"  🎫 Fetching issues...")
    issues = github_api_get(url, params)
    
    if not isinstance(issues, list):
        return []
    
    enriched_issues = []
    for issue in issues:
        if 'pull_request' in issue:
            continue
        
        # Enrich with additional data
        if FEATURES['issue_timeline']:
            issue['timeline'] = fetch_issue_timeline(repo, issue['number'])
        if FEATURES['issue_comments']:
            issue['comment_data'] = fetch_issue_comments(repo, issue['number'])
        if FEATURES['reactions']:
            issue['reactions'] = fetch_reactions(repo, 'issues', issue['number'])
        
        enriched_issues.append(issue)
    
    return enriched_issues

def fetch_issue_timeline(repo, issue_number):
    """Fetch issue timeline events (state changes, assignments, etc.)"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues/{issue_number}/timeline'
    timeline = github_api_get(url)
    return timeline if isinstance(timeline, list) else []

def fetch_issue_comments(repo, issue_number):
    """Fetch issue comments"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/issues/{issue_number}/comments'
    comments = github_api_get(url)
    return comments if isinstance(comments, list) else []

def fetch_reactions(repo, item_type, item_number):
    """Fetch reactions for issues/PRs"""
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/{item_type}/{item_number}/reactions'
    headers = {**HEADERS, 'Accept': 'application/vnd.github.squirrel-girl-preview+json'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        reactions = response.json()
        return reactions if isinstance(reactions, list) else []
    except:
        return []

# ============================================================================
# MILESTONE DATA
# ============================================================================

def fetch_milestones(repo):
    """Fetch all milestones with detailed progress"""
    if not FEATURES['issue_milestones']:
        return []
    
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/milestones'
    params = {'state': 'all', 'per_page': 100}
    print(f"  🎯 Fetching milestones...")
    milestones = github_api_get(url, params)
    return milestones if isinstance(milestones, list) else []

# ============================================================================
# LABEL DATA
# ============================================================================

def fetch_labels(repo):
    """Fetch all repository labels"""
    if not FEATURES['issue_labels']:
        return []
    
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/labels'
    print(f"  🏷️  Fetching labels...")
    labels = github_api_get(url)
    return labels if isinstance(labels, list) else []

# ============================================================================
# PROJECT BOARDS (CLASSIC)
# ============================================================================

def fetch_projects(repo):
    """Fetch classic GitHub Projects (deprecated but still useful)"""
    if not FEATURES['projects']:
        return []
    
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/projects'
    params = {'per_page': 10}
    print(f"  📊 Fetching classic project boards...")
    projects = github_api_get(url, params)
    
    if not isinstance(projects, list):
        return []
    
    projects_data = []
    for project in projects:
        columns_url = f"https://api.github.com/projects/{project['id']}/columns"
        columns = github_api_get(columns_url)
        
        if not isinstance(columns, list):
            continue
        
        columns_data = []
        for column in columns:
            cards_url = f"https://api.github.com/projects/columns/{column['id']}/cards"
            cards = github_api_get(cards_url)
            
            card_details = []
            for card in (cards if isinstance(cards, list) else []):
                card_details.append({
                    'note': card.get('note'),
                    'content_url': card.get('content_url'),
                    'created_at': card.get('created_at'),
                    'updated_at': card.get('updated_at')
                })
            
            columns_data.append({
                'name': column['name'],
                'card_count': len(card_details),
                'cards': card_details
            })
        
        projects_data.append({
            'name': project['name'],
            'state': project['state'],
            'created_at': project.get('created_at'),
            'updated_at': project.get('updated_at'),
            'columns': columns_data
        })
    
    return projects_data

# ============================================================================
# PROJECTS V2 (NEW GITHUB PROJECTS - GRAPHQL)
# ============================================================================

def fetch_projects_v2(repo):
    """Fetch new GitHub Projects V2 via GraphQL"""
    if not FEATURES['projects_v2']:
        return []
    
    print(f"  📊 Fetching Projects V2...")
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        projectsV2(first: 10) {
          nodes {
            title
            shortDescription
            public
            closed
            createdAt
            updatedAt
            items(first: 100) {
              totalCount
              nodes {
                type
                fieldValues(first: 20) {
                  nodes {
                    ... on ProjectV2ItemFieldTextValue {
                      text
                      field {
                        ... on ProjectV2FieldCommon {
                          name
                        }
                      }
                    }
                    ... on ProjectV2ItemFieldSingleSelectValue {
                      name
                      field {
                        ... on ProjectV2FieldCommon {
                          name
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    
    variables = {'owner': ORG_NAME, 'repo': repo}
    result = github_graphql_query(query, variables)
    
    try:
        return result.get('data', {}).get('repository', {}).get('projectsV2', {}).get('nodes', [])
    except:
        return []

# ============================================================================
# ADDITIONAL STATISTICS
# ============================================================================

def fetch_repo_languages(repo):
    """Fetch programming languages"""
    if not FEATURES['languages']:
        return {}
    print(f"  💻 Fetching languages...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/languages'
    return github_api_get(url)

def fetch_code_frequency(repo):
    """Fetch code frequency stats"""
    if not FEATURES['code_frequency']:
        return []
    print(f"  📊 Fetching code frequency...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/stats/code_frequency'
    return github_api_get(url)

def fetch_commit_activity(repo):
    """Fetch commit activity stats"""
    if not FEATURES['commit_activity']:
        return []
    print(f"  📈 Fetching commit activity...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/stats/commit_activity'
    return github_api_get(url)

def fetch_contributors_stats(repo):
    """Fetch contributor statistics"""
    if not FEATURES['contributors']:
        return []
    print(f"  👥 Fetching contributor stats...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/stats/contributors'
    return github_api_get(url)

def fetch_releases(repo):
    """Fetch release history"""
    if not FEATURES['release_notes']:
        return []
    print(f"  🚀 Fetching releases...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/releases'
    releases = github_api_get(url)
    return releases if isinstance(releases, list) else []

def fetch_deployments(repo):
    """Fetch deployment history"""
    if not FEATURES['deployment']:
        return []
    print(f"  🌐 Fetching deployments...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/deployments'
    deployments = github_api_get(url)
    return deployments if isinstance(deployments, list) else []

def fetch_workflow_runs(repo):
    """Fetch GitHub Actions workflow runs"""
    if not FEATURES['workflow_runs']:
        return []
    print(f"  ⚙️  Fetching workflow runs...")
    url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/actions/runs'
    runs = github_api_get(url)
    return runs.get('workflow_runs', []) if isinstance(runs, dict) else []

def fetch_traffic(repo):
    """Fetch repository traffic stats (requires push access)"""
    if not FEATURES['traffic']:
        return {}
    print(f"  📊 Fetching traffic stats...")
    views_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/traffic/views'
    clones_url = f'https://api.github.com/repos/{ORG_NAME}/{repo}/traffic/clones'
    
    return {
        'views': github_api_get(views_url),
        'clones': github_api_get(clones_url)
    }

# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================

def analyze_issue_types(issues):
    """Categorize issues by type (bug, feature, enhancement, etc.)"""
    if not FEATURES['issue_types']:
        return {}
    
    type_counts = Counter()
    type_keywords = {
        'bug': ['bug', 'fix', 'error', 'broken'],
        'feature': ['feature', 'enhancement', 'new'],
        'documentation': ['docs', 'documentation'],
        'question': ['question', 'help'],
        'performance': ['performance', 'speed', 'optimization'],
        'security': ['security', 'vulnerability'],
        'test': ['test', 'testing'],
        'refactor': ['refactor', 'cleanup']
    }
    
    for issue in issues:
        labels = [label['name'].lower() for label in issue.get('labels', [])]
        title = issue.get('title', '').lower()
        
        issue_type = 'other'
        for type_name, keywords in type_keywords.items():
            if any(keyword in ' '.join(labels + [title]) for keyword in keywords):
                issue_type = type_name
                break
        
        type_counts[issue_type] += 1
    
    return dict(type_counts)

def analyze_issue_priority(issues):
    """Analyze issues by priority level"""
    if not FEATURES['priority_analysis']:
        return {}
    
    priority_counts = Counter()
    for issue in issues:
        labels = [label['name'].lower() for label in issue.get('labels', [])]
        
        priority = 'unset'
        for label in labels:
            if 'priority' in label or 'p0' in label or 'p1' in label or 'p2' in label or 'p3' in label:
                priority = label
                break
            if 'critical' in label:
                priority = 'critical'
                break
            if 'high' in label:
                priority = 'high'
                break
            if 'low' in label:
                priority = 'low'
                break
        
        priority_counts[priority] += 1
    
    return dict(priority_counts)

def analyze_blocked_issues(issues):
    """Find blocked or waiting issues"""
    if not FEATURES['blocked_issues']:
        return []
    
    blocked = []
    for issue in issues:
        labels = [label['name'].lower() for label in issue.get('labels', [])]
        if any(keyword in ' '.join(labels) for keyword in ['blocked', 'waiting', 'on-hold']):
            blocked.append(issue)
    
    return blocked

def calculate_time_metrics(issues):
    """Calculate time-based metrics for issues"""
    if not FEATURES['time_tracking']:
        return {}
    
    resolution_times = []
    for issue in issues:
        if issue.get('closed_at'):
            created = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            closed = datetime.fromisoformat(issue['closed_at'].replace('Z', '+00:00'))
            resolution_times.append((closed - created).total_seconds() / 3600)  # hours
    
    if not resolution_times:
        return {}
    
    return {
        'avg_resolution_hours': sum(resolution_times) / len(resolution_times),
        'min_resolution_hours': min(resolution_times),
        'max_resolution_hours': max(resolution_times),
        'total_resolved': len(resolution_times)
    }

def calculate_pr_cycle_time(pull_requests):
    """Calculate PR cycle time metrics"""
    if not FEATURES['pr_cycle_time']:
        return {}
    
    cycle_times = []
    for pr in pull_requests:
        if pr.get('merged_at'):
            created = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
            merged = datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00'))
            cycle_times.append((merged - created).total_seconds() / 3600)  # hours
    
    if not cycle_times:
        return {}
    
    return {
        'avg_cycle_hours': sum(cycle_times) / len(cycle_times),
        'min_cycle_hours': min(cycle_times),
        'max_cycle_hours': max(cycle_times),
        'total_merged': len(cycle_times)
    }

def calculate_team_velocity(issues, pull_requests):
    """Calculate sprint velocity metrics"""
    if not FEATURES['team_velocity']:
        return {}
    
    closed_issues = len([i for i in issues if i.get('closed_at')])
    merged_prs = len([pr for pr in pull_requests if pr.get('merged_at')])
    
    story_points = 0
    for issue in issues:
        if issue.get('closed_at'):
            labels = [label['name'].lower() for label in issue.get('labels', [])]
            for label in labels:
                if 'points' in label or 'sp' in label:
                    try:
                        points = int(''.join(filter(str.isdigit, label)))
                        story_points += points
                    except:
                        pass
    
    return {
        'closed_issues': closed_issues,
        'merged_prs': merged_prs,
        'story_points': story_points,
        'velocity_score': closed_issues + merged_prs
    }

# ============================================================================
# MARKDOWN GENERATION
# ============================================================================

def generate_markdown(all_data, week_range):
    """Generate comprehensive markdown report"""
    start, end = week_range
    week_num = get_week_number(end)
    year = end.year
    
    md = [
        f"# 📊 Sprint Engineering Report - Week {week_num}, {year}\n\n",
        f"**Organization:** `{ORG_NAME}`  \n",
        f"**Report Period:** {format_date(start)} to {format_date(end)}  \n",
        f"**Generated:** {format_datetime(end)}  \n",
        "\n---\n\n"
    ]
    
    # Executive Summary
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_prs = sum(len(repo['pull_requests']) for repo in all_data)
    total_issues = sum(len(repo['issues']) for repo in all_data)
    merged_prs = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at')]) for repo in all_data)
    closed_issues = sum(len([i for i in repo['issues'] if i.get('closed_at')]) for repo in all_data)
    open_issues = total_issues - closed_issues
    
    md.extend([
        "## 📈 Executive Summary\n\n",
        "| Metric | Count |\n",
        "|--------|-------|\n",
        f"| 📝 Total Commits | {total_commits} |\n",
        f"| 🔀 Pull Requests | {total_prs} ({merged_prs} merged) |\n",
        f"| 🎫 Issues Created | {total_issues} |\n",
        f"| ✅ Issues Closed | {closed_issues} |\n",
        f"| 🔄 Issues Open | {open_issues} |\n",
        f"| 📦 Active Repos | {len([r for r in all_data if len(r['commits']) > 0])}/{len(REPOS)} |\n\n"
    ])
    
    # Repository Details
    for repo_data in all_data:
        repo_name = repo_data['name']
        md.append(f"## 📦 {repo_name.capitalize()}\n\n")
        
        # === ISSUES/TICKETS SECTION ===
        if FEATURES['issues'] and repo_data['issues']:
            md.append("### 🎫 Issue Tracking (Tickets)\n\n")
            
            issues = repo_data['issues']
            open_issues = [i for i in issues if i['state'] == 'open']
            closed_issues = [i for i in issues if i['state'] == 'closed']
            
            md.extend([
                "**Issue Status:**\n\n",
                "| Status | Count |\n",
                "|--------|-------|\n",
                f"| 🔄 Open | {len(open_issues)} |\n",
                f"| ✅ Closed | {len(closed_issues)} |\n",
                f"| 📊 Total | {len(issues)} |\n\n"
            ])
            
            # Issue Types
            if FEATURES['issue_types']:
                issue_types = analyze_issue_types(issues)
                if issue_types:
                    md.append("**Issue Types:**\n\n")
                    for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True):
                        md.append(f"- {issue_type.capitalize()}: {count}\n")
                    md.append("\n")
            
            # Priority Analysis
            if FEATURES['priority_analysis']:
                priorities = analyze_issue_priority(issues)
                if priorities:
                    md.append("**Priority Distribution:**\n\n")
                    for priority, count in sorted(priorities.items(), key=lambda x: x[1], reverse=True):
                        md.append(f"- {priority.capitalize()}: {count}\n")
                    md.append("\n")
            
            # Blocked Issues
            if FEATURES['blocked_issues']:
                blocked = analyze_blocked_issues(issues)
                if blocked:
                    md.append(f"**⚠️ Blocked/Waiting Issues: {len(blocked)}**\n\n")
                    for issue in blocked[:5]:
                        md.append(f"- [#{issue['number']}]({issue['html_url']}) {issue['title']}\n")
                    md.append("\n")
            
            # Detailed Issue List
            md.append("**Issue Details:**\n\n")
            for issue in issues[:20]:
                status_icon = "✅" if issue['state'] == 'closed' else "🔄"
                
                # Labels
                labels_str = ", ".join([f"`{l['name']}`" for l in issue.get('labels', [])])
                
                # Assignees
                assignees_str = ""
                if FEATURES['issue_assignees'] and issue.get('assignees'):
                    assignees = ", ".join([f"@{a['login']}" for a in issue['assignees']])
                    assignees_str = f" • Assigned to: {assignees}"
                
                # Milestone
                milestone_str = ""
                if FEATURES['issue_milestones'] and issue.get('milestone'):
                    milestone_str = f" • Milestone: `{issue['milestone']['title']}`"
                
                # Comments
                comments_str = f" • {issue.get('comments', 0)} comments" if issue.get('comments', 0) > 0 else ""
                
                md.append(f"{status_icon} **[#{issue['number']}]({issue['html_url']})** - {issue['title']}  \n")
                if labels_str:
                    md.append(f"  Labels: {labels_str}  \n")
                if assignees_str or milestone_str or comments_str:
                    md.append(f"  {assignees_str}{milestone_str}{comments_str}  \n")
                md.append(f"  *Created: {issue['created_at'][:10]} by @{issue.get('user', {}).get('login', 'unknown')}*\n\n")
            
            if len(issues) > 20:
                md.append(f"*...and {len(issues) - 20} more issues*\n\n")
        
        # === MILESTONES ===
        if FEATURES['milestones_detail'] and repo_data.get('milestones'):
            md.append("### 🎯 Milestones\n\n")
            for milestone in repo_data['milestones']:
                progress = (milestone['closed_issues'] / milestone['open_issues'] * 100) if milestone['open_issues'] > 0 else 100
                state_icon = "✅" if milestone['state'] == 'closed' else "🔄"
                
                md.append(f"{state_icon} **{milestone['title']}** - {progress:.0f}% complete  \n")
                md.append(f"  {milestone['closed_issues']}/{milestone['open_issues']} issues closed  \n")
                if milestone.get('due_on'):
                    md.append(f"  Due: {milestone['due_on'][:10]}  \n")
                md.append("\n")
        
        # === LABELS ===
        if FEATURES['issue_labels'] and repo_data.get('labels'):
            md.append("### 🏷️ Labels\n\n")
            md.append(f"Total labels: {len(repo_data['labels'])}\n\n")
            for label in repo_data['labels'][:15]:
                md.append(f"- **{label['name']}** (#{label.get('color', '000000')}) - {label.get('description', 'No description')}\n")
            md.append("\n")
        
        # === PROJECT BOARDS ===
        if FEATURES['projects'] and repo_data.get('projects'):
            md.append("### 📋 Project Boards (Classic)\n\n")
            for project in repo_data['projects']:
                state_icon = "✅" if project['state'] == 'closed' else "🔄"
                md.append(f"{state_icon} **{project['name']}** - {project['state']}  \n")
                md.append(f"  Created: {project.get('created_at', 'N/A')[:10]}  \n\n")
                
                md.append("**Columns:**\n\n")
                for column in project['columns']:
                    md.append(f"- **{column['name']}**: {column['card_count']} cards\n")
                md.append("\n")
        
        # === PROJECTS V2 ===
        if FEATURES['projects_v2'] and repo_data.get('projects_v2'):
            md.append("### 📊 Projects V2 (New GitHub Projects)\n\n")
            for project in repo_data['projects_v2']:
                status = "🔒 Closed" if project.get('closed') else "🔄 Active"
                visibility = "🌐 Public" if project.get('public') else "🔒 Private"
                
                md.append(f"**{project['title']}** - {status} {visibility}  \n")
                if project.get('shortDescription'):
                    md.append(f"  {project['shortDescription']}  \n")
                md.append(f"  Total items: {project.get('items', {}).get('totalCount', 0)}  \n\n")
        
        # === PULL REQUESTS ===
        if FEATURES['pull_requests'] and repo_data['pull_requests']:
            md.append("### 🔀 Pull Requests\n\n")
            
            prs = repo_data['pull_requests']
            merged = [pr for pr in prs if pr.get('merged_at')]
            open_prs = [pr for pr in prs if pr['state'] == 'open']
            closed_not_merged = [pr for pr in prs if pr['state'] == 'closed' and not pr.get('merged_at')]
            
            md.extend([
                "| Status | Count |\n",
                "|--------|-------|\n",
                f"| ✅ Merged | {len(merged)} |\n",
                f"| 🔄 Open | {len(open_prs)} |\n",
                f"| ❌ Closed (not merged) | {len(closed_not_merged)} |\n\n"
            ])
            
            # PR Cycle Time
            if FEATURES['pr_cycle_time']:
                cycle_metrics = calculate_pr_cycle_time(prs)
                if cycle_metrics:
                    md.append("**⏱️ PR Cycle Time:**\n\n")
                    md.append(f"- Average: {cycle_metrics['avg_cycle_hours']:.1f} hours\n")
                    md.append(f"- Fastest: {cycle_metrics['min_cycle_hours']:.1f} hours\n")
                    md.append(f"- Slowest: {cycle_metrics['max_cycle_hours']:.1f} hours\n\n")
            
            # Detailed PR List
            for pr in prs[:15]:
                status_icon = "✅" if pr.get('merged_at') else ("🔄" if pr['state'] == 'open' else "❌")
                
                reviews_str = ""
                if FEATURES['pr_reviews'] and pr.get('review_data'):
                    approved = len([r for r in pr['review_data'] if r.get('state') == 'APPROVED'])
                    requested_changes = len([r for r in pr['review_data'] if r.get('state') == 'CHANGES_REQUESTED'])
                    reviews_str = f" • {approved} approved, {requested_changes} changes requested"
                
                comments_str = ""
                if FEATURES['pr_comments'] and pr.get('comment_data'):
                    comments_str = f" • {len(pr['comment_data'])} review comments"
                
                md.append(f"{status_icon} **[PR #{pr['number']}]({pr['html_url']})** - {pr['title']}  \n")
                md.append(f"  +{pr.get('additions', 0)}/-{pr.get('deletions', 0)} lines • {pr.get('changed_files', 0)} files • {pr.get('commits', 0)} commits{reviews_str}{comments_str}  \n")
                md.append(f"  *by @{pr.get('user', {}).get('login', 'unknown')}*\n\n")
            
            if len(prs) > 15:
                md.append(f"*...and {len(prs) - 15} more PRs*\n\n")
        
        # === COMMITS ===
        if FEATURES['commits'] and repo_data['commits']:
            md.append("### 📝 Commits\n\n")
            commits = repo_data['commits']
            
            total_additions = sum(c.get('stats', {}).get('additions', 0) for c in commits)
            total_deletions = sum(c.get('stats', {}).get('deletions', 0) for c in commits)
            total_files = sum(len(c.get('files', [])) for c in commits)
            
            md.extend([
                f"**Total:** {len(commits)} commits  \n",
                f"**Code Changes:** +{total_additions:,}/-{total_deletions:,} lines  \n",
                f"**Files Changed:** {total_files}  \n\n",
                "**Recent Commits:**\n\n"
            ])
            
            for commit in commits[:10]:
                if commit and 'commit' in commit:
                    sha = commit['sha'][:7]
                    message = commit['commit']['message'].split('\n')[0][:80]
                    author = commit['commit']['author']['name']
                    additions = commit.get('stats', {}).get('additions', 0)
                    deletions = commit.get('stats', {}).get('deletions', 0)
                    
                    md.append(f"- [`{sha}`]({commit.get('html_url', '#')}) {message}  \n")
                    md.append(f"  *{author} • +{additions}/-{deletions}*\n\n")
        
        # === LANGUAGES ===
        if FEATURES['languages'] and repo_data.get('languages'):
            md.append("### 💻 Languages\n\n")
            total_bytes = sum(repo_data['languages'].values())
            for lang, bytes_count in sorted(repo_data['languages'].items(), key=lambda x: x[1], reverse=True):
                percentage = (bytes_count / total_bytes * 100) if total_bytes > 0 else 0
                md.append(f"- **{lang}**: {percentage:.1f}% ({bytes_count:,} bytes)\n")
            md.append("\n")
        
        # === RELEASES ===
        if FEATURES['release_notes'] and repo_data.get('releases'):
            md.append("### 🚀 Releases\n\n")
            for release in repo_data['releases'][:5]:
                pre_tag = " (pre-release)" if release.get('prerelease') else ""
                draft_tag = " (draft)" if release.get('draft') else ""
                
                md.append(f"- **[{release['tag_name']}]({release['html_url']})** - {release['name']}{pre_tag}{draft_tag}  \n")
                md.append(f"  Published: {release.get('published_at', 'N/A')[:10]}  \n\n")
        
        # === DEPLOYMENTS ===
        if FEATURES['deployment'] and repo_data.get('deployments'):
            md.append("### 🌐 Deployments\n\n")
            for deployment in repo_data['deployments'][:10]:
                md.append(f"- **{deployment.get('environment', 'unknown')}** - {deployment.get('ref', 'N/A')}  \n")
                md.append(f"  Created: {deployment.get('created_at', 'N/A')[:10]}  \n\n")
        
        # === WORKFLOW RUNS ===
        if FEATURES['workflow_runs'] and repo_data.get('workflow_runs'):
            md.append("### ⚙️ GitHub Actions\n\n")
            
            runs = repo_data['workflow_runs']
            success = len([r for r in runs if r.get('conclusion') == 'success'])
            failure = len([r for r in runs if r.get('conclusion') == 'failure'])
            
            md.extend([
                f"**Total Runs:** {len(runs)}  \n",
                f"**Success:** {success} ✅  \n",
                f"**Failure:** {failure} ❌  \n\n",
                "**Recent Runs:**\n\n"
            ])
            
            for run in runs[:10]:
                status_icon = "✅" if run.get('conclusion') == 'success' else "❌"
                md.append(f"- {status_icon} **{run.get('name', 'Unknown')}** - {run.get('status', 'unknown')}  \n")
                md.append(f"  {run.get('head_branch', 'unknown')} • {run.get('created_at', 'N/A')[:10]}  \n\n")
        
        # === TRAFFIC ===
        if FEATURES['traffic'] and repo_data.get('traffic'):
            traffic = repo_data['traffic']
            md.append("### 📊 Repository Traffic\n\n")
            
            if traffic.get('views'):
                views_data = traffic['views']
                md.append(f"**Views:** {views_data.get('count', 0)} total ({views_data.get('uniques', 0)} unique)  \n")
            
            if traffic.get('clones'):
                clones_data = traffic['clones']
                md.append(f"**Clones:** {clones_data.get('count', 0)} total ({clones_data.get('uniques', 0)} unique)  \n")
            
            md.append("\n")
        
        md.append("---\n\n")
    
    # === TEAM ANALYTICS ===
    md.append("## 👥 Team Analytics\n\n")
    
    # Calculate overall team velocity
    all_issues = [issue for repo in all_data for issue in repo['issues']]
    all_prs = [pr for repo in all_data for pr in repo['pull_requests']]
    
    if FEATURES['team_velocity']:
        velocity = calculate_team_velocity(all_issues, all_prs)
        md.extend([
            "### 🚀 Sprint Velocity\n\n",
            f"- **Issues Closed:** {velocity['closed_issues']}\n",
            f"- **PRs Merged:** {velocity['merged_prs']}\n",
            f"- **Story Points:** {velocity['story_points']}\n",
            f"- **Velocity Score:** {velocity['velocity_score']}\n\n"
        ])
    
    if FEATURES['time_tracking']:
        time_metrics = calculate_time_metrics(all_issues)
        if time_metrics:
            md.extend([
                "### ⏱️ Time Metrics\n\n",
                f"- **Average Resolution Time:** {time_metrics['avg_resolution_hours']:.1f} hours\n",
                f"- **Fastest Resolution:** {time_metrics['min_resolution_hours']:.1f} hours\n",
                f"- **Slowest Resolution:** {time_metrics['max_resolution_hours']:.1f} hours\n",
                f"- **Total Resolved:** {time_metrics['total_resolved']}\n\n"
            ])
    
    # Contributor summary
    if FEATURES['contributors']:
        all_contributors = defaultdict(lambda: {
            'commits': 0, 'prs': 0, 'issues': 0, 'reviews': 0, 'repos': set()
        })
        
        for repo_data in all_data:
            for commit in repo_data['commits']:
                if commit and 'commit' in commit:
                    author = commit['commit']['author']['name']
                    all_contributors[author]['commits'] += 1
                    all_contributors[author]['repos'].add(repo_data['name'])
            
            for pr in repo_data['pull_requests']:
                if pr.get('user'):
                    user = pr['user']['login']
                    all_contributors[user]['prs'] += 1
                    all_contributors[user]['repos'].add(repo_data['name'])
                
                if pr.get('review_data'):
                    for review in pr['review_data']:
                        if review.get('user'):
                            reviewer = review['user']['login']
                            all_contributors[reviewer]['reviews'] += 1
                            all_contributors[reviewer]['repos'].add(repo_data['name'])
            
            for issue in repo_data['issues']:
                if issue.get('user'):
                    user = issue['user']['login']
                    all_contributors[user]['issues'] += 1
                    all_contributors[user]['repos'].add(repo_data['name'])
        
        md.append("### 👤 Top Contributors\n\n")
        md.append("| Contributor | Commits | PRs | Issues | Reviews | Repos |\n")
        md.append("|-------------|---------|-----|--------|---------|-------|\n")
        
        sorted_contributors = sorted(
            all_contributors.items(),
            key=lambda x: x[1]['commits'] + x[1]['prs'],
            reverse=True
        )
        
        for name, stats in sorted_contributors[:15]:
            repos_str = ', '.join(sorted(stats['repos']))
            md.append(
                f"| {name} | {stats['commits']} | {stats['prs']} | "
                f"{stats['issues']} | {stats['reviews']} | {repos_str} |\n"
            )
        md.append("\n")
    
    # === KEY INSIGHTS ===
    md.append("## 💡 Key Insights\n\n")
    
    insights = []
    
    # Calculate closed issues count
    total_closed_issues = sum(len([i for i in repo['issues'] if i.get('closed_at')]) for repo in all_data)
    total_open_issues = sum(len([i for i in repo['issues'] if i['state'] == 'open']) for repo in all_data)
    
    if merged_prs > 10:
        insights.append(f"🎉 High PR merge rate: {merged_prs} PRs merged this week")
    
    if total_closed_issues > 15:
        insights.append(f"✅ Excellent issue resolution: {total_closed_issues} issues closed")
    
    blocked = []
    for repo in all_data:
        blocked.extend(analyze_blocked_issues(repo['issues']))
    if blocked:
        insights.append(f"⚠️ {len(blocked)} issues are currently blocked - attention needed")
    
    if total_open_issues > total_closed_issues * 2:
        insights.append(f"📈 Issue backlog growing: {total_open_issues} open vs {total_closed_issues} closed")
    
    if total_commits > 100:
        insights.append(f"🚀 High development activity: {total_commits} commits")
    
    if insights:
        for insight in insights:
            md.append(f"- {insight}\n")
    else:
        md.append("- 📊 Steady progress across all repositories\n")
    
    md.append("\n")
    
    # === FOOTER ===
    md.extend([
        "---\n\n",
        f"*📄 Generated: {format_datetime(end)}*  \n",
        f"*🤖 GitHub Sprint Reporter v2.0*  \n",
        f"*🔧 Powered by GitHub REST API + GraphQL*\n"
    ])
    
    return ''.join(md)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    print("🚀 Starting enhanced sprint report generation...")
    print(f"📦 Organization: {ORG_NAME}")
    print(f"🎯 Repositories: {', '.join(REPOS)}\n")
    
    # Show enabled features
    enabled_features = [k for k, v in FEATURES.items() if v]
    print(f"✨ Enabled features ({len(enabled_features)}):")
    for feature in enabled_features[:10]:
        print(f"   ✓ {feature}")
    if len(enabled_features) > 10:
        print(f"   ... and {len(enabled_features) - 10} more")
    print()
    
    start, end = get_week_range()
    print(f"📅 Period: {format_date(start)} to {format_date(end)}\n")
    
    all_data = []
    
    for repo in REPOS:
        print(f"📦 Processing {repo}...")
        
        # Fetch all data
        commits = fetch_commits(repo, start, end)
        pull_requests = fetch_pull_requests(repo, start)
        issues = fetch_issues(repo, start)
        milestones = fetch_milestones(repo)
        labels = fetch_labels(repo)
        projects = fetch_projects(repo)
        projects_v2 = fetch_projects_v2(repo)
        languages = fetch_repo_languages(repo)
        contributors_stats = fetch_contributors_stats(repo)
        code_frequency = fetch_code_frequency(repo)
        commit_activity = fetch_commit_activity(repo)
        releases = fetch_releases(repo)
        deployments = fetch_deployments(repo)
        workflow_runs = fetch_workflow_runs(repo)
        traffic = fetch_traffic(repo)
        
        print(f"  ✓ {len(commits)} commits")
        print(f"  ✓ {len(pull_requests)} PRs")
        print(f"  ✓ {len(issues)} issues")
        print(f"  ✓ {len(milestones)} milestones")
        print(f"  ✓ {len(labels)} labels")
        print(f"  ✓ {len(projects)} classic projects")
        print(f"  ✓ {len(projects_v2)} projects v2")
        print()
        
        all_data.append({
            'name': repo,
            'commits': commits,
            'pull_requests': pull_requests,
            'issues': issues,
            'milestones': milestones,
            'labels': labels,
            'projects': projects,
            'projects_v2': projects_v2,
            'languages': languages if isinstance(languages, dict) else {},
            'contributors_stats': contributors_stats if isinstance(contributors_stats, list) else [],
            'code_frequency': code_frequency if isinstance(code_frequency, list) else [],
            'commit_activity': commit_activity if isinstance(commit_activity, list) else [],
            'releases': releases,
            'deployments': deployments,
            'workflow_runs': workflow_runs,
            'traffic': traffic
        })
    
    # Generate markdown
    print("📝 Generating comprehensive sprint report...")
    markdown = generate_markdown(all_data, (start, end))
    
    # Save report
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)
    
    week_num = get_week_number(end)
    year = end.year
    filename = f"sprint-week-{week_num}-{year}.md"
    filepath = reports_dir / filename
    
    filepath.write_text(markdown, encoding='utf-8')
    print(f"✅ Report saved: reports/{filename}")
    print(f"📊 Size: {len(markdown):,} characters\n")
    
    # Update latest
    latest_path = reports_dir / 'latest.md'
    latest_path.write_text(markdown, encoding='utf-8')
    print(f"✅ Latest updated: reports/latest.md")
    
    print("\n🎉 Sprint report generation complete!")
    print(f"📈 Total data points collected: {sum(len(repo['issues']) + len(repo['pull_requests']) + len(repo['commits']) for repo in all_data)}")

if __name__ == '__main__':
    main()