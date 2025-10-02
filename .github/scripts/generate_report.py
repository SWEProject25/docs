#!/usr/bin/env python3

import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import requests
from pathlib import Path
import math
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, HRFlowable, Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus.flowables import KeepTogether
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
import google.generativeai as genai
from PyPDF2 import PdfReader


# Configuration
GITHUB_TOKEN = os.environ.get('PAT_TOCKEN')
ORG_NAME = os.environ.get('ORG_NAME') 
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
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

# --- Project Requirements Extraction ---

def read_requirement_pdfs():
    """Read all PDF files from src/requirement folder and extract text."""
    requirement_text = ""
    
    # Look for requirement PDFs in common locations
    possible_paths = [
        Path('resources'),  # Primary location
        Path('src/requirement'),
        Path('requirement'),
        Path('requirements'),
        Path('docs/requirements'),
        Path('.')
    ]
    
    pdf_files = []
    for path in possible_paths:
        if path.exists() and path.is_dir():
            pdf_files.extend(list(path.glob('*.pdf')))
    
    if not pdf_files:
        print("  ℹ No requirement PDFs found in project folders")
        return None
    
    print(f"  📄 Found {len(pdf_files)} requirement PDF(s)")
    
    for pdf_path in pdf_files:
        try:
            reader = PdfReader(str(pdf_path))
            text = f"\n\n=== {pdf_path.name} ===\n"
            for page in reader.pages:
                text += page.extract_text() + "\n"
            requirement_text += text
            print(f"     ✓ Loaded: {pdf_path.name}")
        except Exception as e:
            print(f"     ⚠ Could not read {pdf_path.name}: {e}")
    
    return requirement_text if requirement_text else None

# --- AI Insights Generation ---

def generate_ai_insights(all_data, start, end):
    """Generate intelligent insights using Google Gemini AI."""
    
    # Prepare data summary for AI analysis
    total_commits = sum(len(repo['commits']) for repo in all_data)
    total_issues_created = sum(len([i for i in repo['issues'] if start <= datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) < end]) for repo in all_data)
    total_issues_closed = sum(len([i for i in repo['issues'] if i.get('closed_at') and start <= datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) < end]) for repo in all_data)
    total_prs_opened = sum(len([pr for pr in repo['pull_requests'] if start <= datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) < end]) for repo in all_data)
    total_prs_merged = sum(len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and start <= datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) < end]) for repo in all_data)
    
    # Analyze contributors
    all_commits = [c for repo in all_data for c in repo['commits']]
    contributors = defaultdict(int)
    for commit in all_commits:
        author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
        contributors[author] += 1
    
    # Analyze issue types
    all_issues = [i for repo in all_data for i in repo['issues'] if start <= datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) < end]
    issue_types = defaultdict(int)
    for issue in all_issues:
        issue_types[get_issue_type(issue)] += 1
    
    # Repository breakdown
    repo_summary = []
    for repo in all_data:
        repo_summary.append({
            'name': repo['name'],
            'commits': len(repo['commits']),
            'issues_created': len([i for i in repo['issues'] if start <= datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) < end]),
            'issues_closed': len([i for i in repo['issues'] if i.get('closed_at') and start <= datetime.fromisoformat(i['closed_at'].replace('Z', '+00:00')) < end]),
            'prs_opened': len([pr for pr in repo['pull_requests'] if start <= datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) < end]),
            'prs_merged': len([pr for pr in repo['pull_requests'] if pr.get('merged_at') and start <= datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) < end])
        })
    
    # Read project requirements
    requirements = read_requirement_pdfs()
    
    # Build prompt for Gemini
    data_summary = f"""GitHub Activity Analysis for Week:

OVERALL METRICS:
- Total Commits: {total_commits}
- Issues Created: {total_issues_created}
- Issues Closed: {total_issues_closed}
- Pull Requests Opened: {total_prs_opened}
- Pull Requests Merged: {total_prs_merged}
- Issue Closure Rate: {(total_issues_closed/total_issues_created*100) if total_issues_created > 0 else 0:.1f}%
- PR Merge Rate: {(total_prs_merged/total_prs_opened*100) if total_prs_opened > 0 else 0:.1f}%

CONTRIBUTOR DISTRIBUTION:
{chr(10).join([f"- {name}: {count} commits" for name, count in sorted(contributors.items(), key=lambda x: x[1], reverse=True)])}

ISSUE TYPES:
{chr(10).join([f"- {itype}: {count}" for itype, count in issue_types.items()])}

REPOSITORY BREAKDOWN:
{chr(10).join([f"- {r['name']}: {r['commits']} commits, {r['issues_created']} issues created, {r['issues_closed']} closed, {r['prs_opened']} PRs opened, {r['prs_merged']} merged" for r in repo_summary])}
"""
    
    # Add project requirements if available
    if requirements:
        data_summary += f"\n\nPROJECT REQUIREMENTS DOCUMENT:\n{requirements[:4000]}"  # Limit to avoid token limits

    # Try to use Gemini AI
    insights = []
    recommendations = []
    
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            
            # List available models from the API
            try:
                available_models = genai.list_models()
                model_names = []
                for m in available_models:
                    # Only use models that support generateContent
                    if 'generateContent' in m.supported_generation_methods:
                        model_names.append(m.name)
                
                if model_names:
                    print(f"  ℹ Found {len(model_names)} available Gemini models")
                else:
                    print("  ⚠ No models with generateContent support found")
            except Exception as e:
                print(f"  ⚠ Could not list models: {e}")
                # Fallback to common model names
                model_names = [
                    'gemini-1.5-flash-latest',
                    'gemini-1.5-flash',
                    'gemini-1.5-pro-latest',
                    'gemini-pro',
                    'models/gemini-1.5-flash',
                    'models/gemini-pro'
                ]
            
            model = None
            last_error = None
            
            for model_name in model_names:
                try:
                    model = genai.GenerativeModel(model_name)
                    # Test the model with a simple prompt
                    test_response = model.generate_content("Test")
                    print(f"  ✓ Using Gemini model: {model_name}")
                    break
                except Exception as e:
                    last_error = str(e)[:100]  # Truncate error
                    continue
            
            if not model:
                raise Exception(f"No working Gemini model found. Last error: {last_error}")
            
            # Build context-aware prompt
            if requirements:
                prompt = f"""{data_summary}

You are a senior technical project manager analyzing a software project. You have access to:
1. The PROJECT REQUIREMENTS document above
2. This week's GitHub activity metrics

Your task:
1. Compare actual progress against the requirements/timeline
2. Identify which project phase/milestone the team should be in
3. Determine if work aligns with project requirements
4. Provide SPECIFIC, ACTIONABLE recommendations (not generic advice)

Provide:

INSIGHTS (4-6 critical observations):
- Compare current work to what SHOULD be happening per requirements
- Identify if team is on track, ahead, or behind schedule
- Note any missing critical features or milestones
- Flag work that doesn't align with project requirements

Format: "[Icon] Title|Description" where Icon is "✓" (on track) or "⚠" (concern)

RECOMMENDATIONS (4-6 specific actions):
- Reference specific features/requirements from the document
- Suggest concrete next steps based on project phase
- Prioritize work that's critical per requirements
- Identify blockers preventing requirement completion

Format exactly as:
INSIGHTS:
✓ Title|Description
⚠ Title|Description

RECOMMENDATIONS:
- Specific action
- Specific action
"""
            else:
                # Fallback prompt without requirements
                prompt = f"""{data_summary}

As a senior software engineering manager, analyze the GitHub activity and provide:

INSIGHTS (4-6 observations): Format as "[Icon] Title|Description" with "✓" or "⚠"

RECOMMENDATIONS (4-6 actions): Specific, actionable recommendations for improvement.

Format exactly as:
INSIGHTS:
✓ Title|Description
⚠ Title|Description

RECOMMENDATIONS:
- Action
- Action
"""
            
            # Generate insights with the working model
            response = model.generate_content(prompt)
            
            # Parse AI response
            text = response.text
            sections = text.split('RECOMMENDATIONS:')
            
            if len(sections) >= 2:
                # Parse insights
                insights_text = sections[0].replace('INSIGHTS:', '').strip()
                for line in insights_text.split('\n'):
                    line = line.strip()
                    if line and ('✓' in line or '⚠' in line):
                        if '|' in line:
                            parts = line.split('|', 1)
                            title = parts[0].strip()
                            desc = parts[1].strip() if len(parts) > 1 else ''
                            insights.append((title, desc))
                
                # Parse recommendations
                recs_text = sections[1].strip()
                for line in recs_text.split('\n'):
                    line = line.strip()
                    if line.startswith('-'):
                        recommendations.append(line[1:].strip())
            
            print("  ✓ AI insights generated successfully using Gemini")
            
        except Exception as e:
            error_msg = str(e)[:200]  # Truncate long errors
            print(f"  ⚠ Gemini API error: {error_msg}")
            print("  ℹ Tip: Get a free API key at https://makersuite.google.com/app/apikey")
            print("  ℹ Falling back to rule-based analysis")
            # Fall back to basic analysis
            insights, recommendations = _fallback_insights(all_data, start, end, total_commits, total_issues_created, total_issues_closed, total_prs_opened, total_prs_merged, contributors, issue_types)
    else:
        print("  ℹ No GEMINI_API_KEY found, using rule-based analysis")
        insights, recommendations = _fallback_insights(all_data, start, end, total_commits, total_issues_created, total_issues_closed, total_prs_opened, total_prs_merged, contributors, issue_types)
    
    return insights, recommendations

def _fallback_insights(all_data, start, end, total_commits, total_issues_created, total_issues_closed, total_prs_opened, total_prs_merged, contributors, issue_types):
    """Fallback rule-based insights when AI is unavailable."""
    insights = []
    recommendations = []
    
    # Basic analysis
    active_repos = [r for r in all_data if len(r['commits']) > 0]
    
    if len(active_repos) / len(all_data) >= 0.8:
        insights.append(("✓ High Activity", f"Excellent! {len(active_repos)}/{len(all_data)} repositories show active development."))
    
    if total_issues_created > 0:
        closure_rate = (total_issues_closed / total_issues_created) * 100
        if closure_rate >= 70:
            insights.append(("✓ Strong Issue Resolution", f"{closure_rate:.0f}% of issues closed this week."))
        elif closure_rate < 30:
            insights.append(("⚠ Growing Backlog", f"Only {closure_rate:.0f}% of issues resolved."))
    
    if total_prs_opened > 0:
        merge_rate = (total_prs_merged / total_prs_opened) * 100
        if merge_rate >= 80:
            insights.append(("✓ Efficient PR Process", f"{merge_rate:.0f}% of PRs merged successfully."))
        elif merge_rate < 40:
            insights.append(("⚠ PR Bottleneck", f"Only {merge_rate:.0f}% merge rate detected."))
    
    if len(contributors) > 0:
        avg = sum(contributors.values()) / len(contributors)
        max_commits = max(contributors.values())
        if max_commits > avg * 3:
            insights.append(("⚠ Unbalanced Load", "Workload distribution needs review."))
    
    # Basic recommendations
    recommendations.append("Consider implementing CI/CD pipelines for faster deployment cycles.")
    recommendations.append("Schedule regular code review sessions to maintain quality standards.")
    recommendations.append("Document architectural decisions for better team alignment.")
    
    return insights, recommendations

# --- PDF Generation Function ---

def generate_dashboards(all_data, start, end, chart_colors, heading3_style):
    """Generate professional, modern charts with premium styling."""
    elements = []

    # Calculate metrics
    repo_names = [capitalize_repo_name(r['name']) for r in all_data]
    commit_counts = [len(r['commits']) for r in all_data]
    issue_counts = [len([i for i in r['issues'] if start <= datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) < end]) for r in all_data]
    pr_counts = [len([p for p in r['pull_requests'] if start <= datetime.fromisoformat(p['created_at'].replace('Z', '+00:00')) < end]) for r in all_data]

    # Professional color palette
    bar_colors = [
        colors.HexColor('#3498db'),  # Blue - Commits
        colors.HexColor('#e74c3c'),  # Red - Issues  
        colors.HexColor('#2ecc71'),  # Green - PRs
    ]
    
    pie_colors = [
        colors.HexColor('#3498db'),  # Blue
        colors.HexColor('#9b59b6'),  # Purple
        colors.HexColor('#e67e22'),  # Orange
        colors.HexColor('#1abc9c'),  # Teal
        colors.HexColor('#f39c12'),  # Yellow
        colors.HexColor('#e74c3c'),  # Red
    ]

    # 1. ACTIVITY BY REPOSITORY - Bar Chart
    elements.append(Paragraph("<b>REPOSITORY ACTIVITY METRICS</b>", heading3_style))
    elements.append(Spacer(1, 0.2*cm))
    
    drawing = Drawing(width=17*cm, height=9*cm)
    data = [commit_counts, issue_counts, pr_counts]
    
    bc = VerticalBarChart()
    bc.x = 40
    bc.y = 50
    bc.height = 180
    bc.width = 380
    bc.data = data
    bc.groupSpacing = 20
    bc.barSpacing = 4
    bc.barWidth = 10

    bc.categoryAxis.categoryNames = repo_names
    bc.categoryAxis.labels.boxAnchor = 'n'
    bc.categoryAxis.labels.angle = 0
    bc.categoryAxis.labels.fontSize = 9
    bc.categoryAxis.labels.dy = -8
    bc.categoryAxis.labels.fontName = 'Helvetica-Bold'
    bc.categoryAxis.strokeWidth = 1
    bc.categoryAxis.strokeColor = colors.HexColor('#34495e')
    
    bc.valueAxis.valueMin = 0
    max_val = max(max(c) for c in data) if any(any(v > 0 for v in c) for c in data) else 1
    bc.valueAxis.valueMax = max_val + 2
    bc.valueAxis.valueStep = max(1, max_val // 5)
    bc.valueAxis.labels.fontSize = 8
    bc.valueAxis.strokeWidth = 1
    bc.valueAxis.strokeColor = colors.HexColor('#34495e')
    bc.valueAxis.gridStart = 40
    bc.valueAxis.gridEnd = 420
    bc.valueAxis.gridStrokeColor = colors.HexColor('#ecf0f1')
    bc.valueAxis.gridStrokeWidth = 0.5

    # Modern bar colors with subtle styling
    for i, color in enumerate(bar_colors):
        bc.bars[i].fillColor = color
        bc.bars[i].strokeColor = colors.white
        bc.bars[i].strokeWidth = 0.5

    drawing.add(bc)

    # Enhanced legend
    legend = Legend()
    legend.x = 430
    legend.y = 140
    legend.alignment = 'right'
    legend.fontSize = 9
    legend.fontName = 'Helvetica-Bold'
    legend.columnMaximum = 3
    legend.dx = 10
    legend.dy = 10
    legend.dxTextSpace = 5
    legend.colorNamePairs = [
        (bar_colors[0], 'Commits'),
        (bar_colors[1], 'Issues'),
        (bar_colors[2], 'Pull Requests')
    ]
    drawing.add(legend)

    elements.append(drawing)
    elements.append(Spacer(1, 0.6*cm))

    # 2. ISSUE & PR BREAKDOWN - Enhanced Pie Charts
    all_issues = [i for repo in all_data for i in repo['issues'] if start <= datetime.fromisoformat(i['created_at'].replace('Z', '+00:00')) < end]
    all_prs = [pr for repo in all_data for pr in repo['pull_requests'] if start <= datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) < end]

    if all_issues or all_prs:
        elements.append(Paragraph("<b>ISSUE & PULL REQUEST DISTRIBUTION</b>", heading3_style))
        elements.append(Spacer(1, 0.2*cm))
        
        pie_drawing = Drawing(width=17*cm, height=8*cm)
        
        # Issue Types Pie Chart
        if all_issues:
            issue_types = defaultdict(int)
            for issue in all_issues:
                issue_types[get_issue_type(issue)] += 1
            
            # Add title for issue pie
            from reportlab.graphics.shapes import String
            title1 = String(140, 220, 'Issue Types', fontSize=10, fontName='Helvetica-Bold', textAnchor='middle')
            pie_drawing.add(title1)
            
            issue_pie = Pie()
            issue_pie.x = 80
            issue_pie.y = 80
            issue_pie.width = 120
            issue_pie.height = 120
            issue_pie.data = list(issue_types.values())
            issue_pie.labels = []
            issue_pie.slices.strokeWidth = 2
            issue_pie.slices.strokeColor = colors.white
            issue_pie.sideLabels = 0
            
            for i in range(len(issue_types)):
                issue_pie.slices[i].fillColor = pie_colors[i % len(pie_colors)]
                issue_pie.slices[i].popout = 3 if i == 0 else 0
            
            pie_drawing.add(issue_pie)
            
            # Enhanced legend for issues
            issue_legend = Legend()
            issue_legend.x = 15
            issue_legend.y = 40
            issue_legend.fontSize = 8
            issue_legend.fontName = 'Helvetica'
            issue_legend.columnMaximum = 1
            issue_legend.dx = 10
            issue_legend.dy = 10
            issue_legend.dxTextSpace = 5
            issue_legend.colorNamePairs = [
                (pie_colors[i % len(pie_colors)], f"{k}: {v}") 
                for i, (k, v) in enumerate(issue_types.items())
            ]
            pie_drawing.add(issue_legend)
        
        # PR Status Pie Chart
        if all_prs:
            pr_status = defaultdict(int)
            for pr in all_prs:
                if pr.get('merged_at') and start <= datetime.fromisoformat(pr['merged_at'].replace('Z', '+00:00')) < end:
                    pr_status['Merged'] += 1
                elif pr['state'] == 'open':
                    pr_status['Open'] += 1
                else:
                    pr_status['Closed'] += 1
            
            # Add title for PR pie
            from reportlab.graphics.shapes import String
            title2 = String(390, 220, 'Pull Request Status', fontSize=10, fontName='Helvetica-Bold', textAnchor='middle')
            pie_drawing.add(title2)
            
            pr_pie = Pie()
            pr_pie.x = 330
            pr_pie.y = 80
            pr_pie.width = 120
            pr_pie.height = 120
            pr_pie.data = list(pr_status.values())
            pr_pie.labels = []
            pr_pie.slices.strokeWidth = 2
            pr_pie.slices.strokeColor = colors.white
            pr_pie.sideLabels = 0
            
            pr_specific_colors = [pie_colors[2], pie_colors[0], pie_colors[1]]  # Green, Blue, Red
            for i in range(len(pr_status)):
                pr_pie.slices[i].fillColor = pr_specific_colors[i % len(pr_specific_colors)]
                pr_pie.slices[i].popout = 3 if i == 0 else 0
            
            pie_drawing.add(pr_pie)
            
            # Enhanced legend for PRs
            pr_legend = Legend()
            pr_legend.x = 265
            pr_legend.y = 40
            pr_legend.fontSize = 8
            pr_legend.fontName = 'Helvetica'
            pr_legend.columnMaximum = 1
            pr_legend.dx = 10
            pr_legend.dy = 10
            pr_legend.dxTextSpace = 5
            pr_legend.colorNamePairs = [
                (pr_specific_colors[i % len(pr_specific_colors)], f"{k}: {v}") 
                for i, (k, v) in enumerate(pr_status.items())
            ]
            pie_drawing.add(pr_legend)
        
        elements.append(pie_drawing)

    return elements

def generate_pdf_report(all_data, week_range):
    """Generate a concise, professional PDF report."""
    
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
    
    # Corporate professional color scheme
    PRIMARY_COLOR = colors.HexColor('#1a1a1a') # Near Black
    SECONDARY_COLOR = colors.HexColor('#2c3e50') # Dark Blue Gray
    ACCENT_COLOR = colors.HexColor('#34495e') # Professional Blue
    HEADER_BG = colors.HexColor('#ecf0f1') # Very Light Gray
    TABLE_HEADER_COLOR_1 = colors.HexColor('#2c3e50') # Dark Blue Gray
    TABLE_HEADER_COLOR_2 = colors.HexColor('#34495e') # Professional Blue
    
    # Custom styles - very compact and formal
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=PRIMARY_COLOR,
        spaceAfter=0.15*cm,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=20
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=SECONDARY_COLOR,
        spaceAfter=0.08*cm,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    meta_style = ParagraphStyle(
        'MetaInfo',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#7f8c8d'),
        spaceAfter=0.4*cm,
        alignment=TA_CENTER
    )
    
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=PRIMARY_COLOR,
        spaceAfter=0.3*cm,
        spaceBefore=0.6*cm,
        fontName='Helvetica-Bold',
        leftIndent=0
    )
    
    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=SECONDARY_COLOR,
        spaceAfter=0.2*cm,
        spaceBefore=0.4*cm,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#2c3e50'),
        alignment=TA_JUSTIFY,
        spaceAfter=0.15*cm,
        leading=10
    )

    table_cell_style_small = ParagraphStyle(
        'TableCellSmall',
        parent=styles['Normal'],
        fontSize=6.5,
        leading=7.5,
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
    
    # Add note about clickable elements
    clickable_note = Paragraph(
        "<i><b>Note:</b> Click on repository names, issue/PR numbers, usernames, and commit SHAs to navigate directly to GitHub</i>", 
        ParagraphStyle('ClickableNote', parent=meta_style, fontSize=8, textColor=colors.HexColor('#3498db'))
    )
    elements.append(clickable_note)
    
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
    
    summary_text = f"""This report provides a concise analysis of development activity for the <link href='https://github.com/{ORG_NAME}'>{ORG_NAME}</link> Social Network project 
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

    # --- Project Dashboards ---
    elements.append(Paragraph("PROJECT DASHBOARDS", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))

    dashboard_elements = generate_dashboards(all_data, start, end, [PRIMARY_COLOR, SECONDARY_COLOR, ACCENT_COLOR, colors.HexColor('#7f8c8d')], heading3_style)
    elements.extend(dashboard_elements)
    
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
        repo_section_elements.append(Paragraph(f"REPOSITORY: <link href='https://github.com/{ORG_NAME}/{repo_name}'>{capitalize_repo_name(repo_name).upper()}</link>", heading2_style))
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
                    Paragraph(f"<link href='{commit.get('author', {}).get('html_url', '#') if commit.get('author') else '#'}'>{author}</link>", table_cell_style_small),
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
                    Paragraph(f"<link href='{issue.get('user', {}).get('html_url', '#')}'>{issue.get('user', {}).get('login', 'N/A')[:12]}</link>", table_cell_style_small),
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
                    Paragraph(f"<link href='{issue.get('closed_by', {}).get('html_url', '#') if issue.get('closed_by') else '#'}'>{closed_by[:15]}</link>", table_cell_style_small),
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
        
        if prs_opened:
            prs_opened_section = []
            prs_opened_section.append(Paragraph("Pull Requests Opened This Week", heading3_style))
            
            prs_data = [['#', 'TITLE', 'AUTHOR', 'STATUS', 'CHANGES', 'REVIEWERS', 'CREATED']]
            for pr in sorted(prs_opened, key=lambda x: x['number'], reverse=True):
                title = pr['title'][:38] + '...' if len(pr['title']) > 38 else pr['title']
                
                if pr.get('merged_at'):
                    status = 'MERGED'
                elif pr['state'] == 'open':
                    status = 'OPEN'
                else:
                    status = 'CLOSED'
                
                changes = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                
                reviewers = []
                if pr.get('requested_reviewers'):
                    reviewers = [r['login'] for r in pr['requested_reviewers'][:1]]
                reviewers_str = ', '.join(reviewers) if reviewers else 'None'
                if len(pr.get('requested_reviewers', [])) > 1:
                    reviewers_str += f' +{len(pr.get("requested_reviewers", [])) - 1}'
                
                pr_url = pr.get('html_url', '#')

                prs_data.append([
                    Paragraph(f"<link href='{pr_url}'>#{pr['number']}</link>", table_cell_style_small),
                    Paragraph(title, table_cell_style_small),
                    Paragraph(f"<link href='{pr.get('user', {}).get('html_url', '#')}'>{pr.get('user', {}).get('login', 'N/A')[:12]}</link>", table_cell_style_small),
                    Paragraph(status, table_cell_style_small),
                    Paragraph(changes, table_cell_style_small),
                    Paragraph(reviewers_str, table_cell_style_small),
                    Paragraph(pr['created_at'][:10], table_cell_style_small)
                ])
            
            prs_table = Table(prs_data, colWidths=[1.2*cm, 4.8*cm, 2.3*cm, 1.8*cm, 2*cm, 2.7*cm, 2.2*cm])
            prs_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ('TOPPADDING', (0, 0), (-1, 0), 5),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#bdc3c7')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            prs_opened_section.append(prs_table)
            prs_opened_section.append(Spacer(1, 0.3*cm))
            elements.append(KeepTogether(prs_opened_section))
        
        if prs_merged:
            prs_merged_section = []
            prs_merged_section.append(Paragraph("Pull Requests Merged This Week", heading3_style))
            
            merged_data = [['#', 'TITLE', 'AUTHOR', 'MERGED BY', 'LINES CHANGED', 'MERGED DATE']]
            for pr in sorted(prs_merged, key=lambda x: x['merged_at'] if x.get('merged_at') else '', reverse=True):
                title = pr['title'][:40] + '...' if len(pr['title']) > 40 else pr['title']
                merged_by = pr.get('merged_by', {}).get('login', 'N/A') if pr.get('merged_by') else pr.get('user', {}).get('login', 'N/A')
                lines_changed = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
                pr_url = pr.get('html_url', '#')

                merged_data.append([
                    Paragraph(f"<link href='{pr_url}'>#{pr['number']}</link>", table_cell_style_small),
                    Paragraph(title, table_cell_style_small),
                    Paragraph(f"<link href='{pr.get('user', {}).get('html_url', '#')}'>{pr.get('user', {}).get('login', 'N/A')[:12]}</link>", table_cell_style_small),
                    Paragraph(f"<link href='{pr.get('merged_by', {}).get('html_url', '#') if pr.get('merged_by') else pr.get('user', {}).get('html_url', '#')}'>{merged_by[:12]}</link>", table_cell_style_small),
                    Paragraph(lines_changed, table_cell_style_small),
                    Paragraph(pr['merged_at'][:10] if pr.get('merged_at') else 'N/A', table_cell_style_small)
                ])
            
            merged_table = Table(merged_data, colWidths=[1.2*cm, 5.8*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            merged_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (4, 0), (4, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
                ('TOPPADDING', (0, 0), (-1, 0), 5),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#bdc3c7')),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            prs_merged_section.append(merged_table)
            prs_merged_section.append(Spacer(1, 0.3*cm))
            elements.append(KeepTogether(prs_merged_section))
        
        elements.append(PageBreak())
    
    # --- AI-Powered Insights & Recommendations ---
    elements.append(Paragraph("AI-POWERED INSIGHTS & RECOMMENDATIONS", heading2_style))
    elements.append(HRFlowable(width="100%", thickness=0.7, color=ACCENT_COLOR, spaceAfter=0.5*cm, spaceBefore=0))
    
    insights, recommendations = generate_ai_insights(all_data, start, end)
    
    # Insights section
    if insights:
        elements.append(Paragraph("Key Insights", heading3_style))
        intro_text = "Our AI analysis has identified the following patterns and observations from this week's activity:"
        elements.append(Paragraph(intro_text, body_style))
        elements.append(Spacer(1, 0.2*cm))
        
        insights_data = [['STATUS', 'INSIGHT']]
        for title, description in insights:
            insights_data.append([
                Paragraph(f"<b>{title}</b>", table_cell_style_small),
                Paragraph(description, table_cell_style_small)
            ])
        
        insights_table = Table(insights_data, colWidths=[4*cm, 13*cm])
        insights_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_1),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(insights_table)
        elements.append(Spacer(1, 0.4*cm))
    
    # Recommendations section
    if recommendations:
        elements.append(Paragraph("Actionable Recommendations", heading3_style))
        rec_text = "Based on the analysis above, here are strategic recommendations to improve team productivity and code quality:"
        elements.append(Paragraph(rec_text, body_style))
        elements.append(Spacer(1, 0.2*cm))
        
        rec_data = [['#', 'RECOMMENDATION']]
        for idx, rec in enumerate(recommendations, 1):
            rec_data.append([
                Paragraph(f"<b>{idx}</b>", table_cell_style_small),
                Paragraph(rec, table_cell_style_small)
            ])
        
        rec_table = Table(rec_data, colWidths=[1*cm, 16*cm])
        rec_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER_COLOR_2),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(rec_table)
    
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
            Paragraph(f"<link href='https://github.com/{member}'>{member[:18]}</link>", table_cell_style_small),
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
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#bdc3c7')),
        ('FONTSIZE', (0, 1), (-1, -1), 6.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HEADER_BG, colors.white]),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    
    elements.append(KeepTogether([team_table, Spacer(1, 0.5*cm)]))
    
    # --- Footer ---
    elements.append(Spacer(1, 1*cm))
    footer_text = f"""<i>This automated report was generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} 
    for the <link href='https://github.com/{ORG_NAME}'><b>{ORG_NAME}</b></link> Social Network Project. Data covers Week {week_num} of {year} 
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
