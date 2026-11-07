"""Deterministically extend 72 original Web UI samples to 150 (6 groups x 25).

Generates 78 *new* standalone HTML pages, structured annotations, preview metadata,
search fallback records, and a static gallery index.  Does not alter the 72
original HTML files or thumbnails.  A separate screenshot script creates WebP.
Run from any working directory: python scripts/expand_to_150.py
"""
from __future__ import annotations
import json
import html
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
BASE = 'https://hcmue.github.io/lokg-web-gallery'
STAMP = '2026-11-07T00:00:00+00:00'

# id prefix, category, Vietnamese heading, accent base, 4 coordinated palettes
GROUPS = {
 'ECO': ('ecommerce','Th\u01b0\u01a1ng m\u1ea1i \u0111i\u1ec7n t\u1eed', ['#d75e63','#4f6eec','#d88a38','#087e7c'], ['#fff2ee','#eff3ff','#fff5e7','#e9f7f3'], ['Fashion','Living','Electronics','Wellness','Lifestyle','Accessories']),
 'EDU': ('education','Gi\u00e1o d\u1ee5c', ['#198e8d','#845fc0','#d98a36','#3b74cb'], ['#eaf8f5','#f6effd','#fff7ed','#ecf4ff'], ['Courses','Learning','Lessons','Mentors','Resources','Students']),
 'BUS': ('business','Doanh nghi\u1ec7p', ['#355f9f','#178274','#ac634e','#7259bd'], ['#edf4fb','#eef8f4','#fff2ed','#f4f0fb'], ['Strategy','Services','Clients','Research','Insights','Projects']),
 'NEW': ('news','Tin t\u1ee9c / Blog', ['#ba5e37','#3a7291','#b84f62','#4b7b64'], ['#fff4ed','#eef4f7','#fff0f3','#eef6f1'], ['Stories','Culture','Technology','People','Research','Perspectives']),
 'LAN': ('landing','Landing Page', ['#7b55c7','#147f91','#db685d','#5f8095'], ['#f4effd','#ebf8fb','#fff0ed','#eef3f8'], ['Features','Benefits','Use Cases','Customer Stories','Plans','Get Started']),
 'DAS': ('dashboard','Dashboard / Bi\u1ec3u m\u1eabu', ['#3268ab','#087c7a','#9358bd','#b66b42'], ['#edf4ff','#e9f7f4','#f5effb','#fff4ea'], ['Overview','Analytics','Reports','Operations','Settings','Team']),
}

# 13 deliberately diverse page types, each reused with distinct content per domain.
# Format: brand | hero title | template | domain labels | extra topic tags
RAW = {
'ECO': [
 'NOVA THREADS|Everyday pieces, thoughtfully selected|split|Outerwear, Essentials, Linen, Studio edit|fashion,clothing,hero',
 'MOSS MARKET|Find your next favorite|catalog-side|Homeware, Lighting, Textiles, Art prints|furniture,filters,sidebar',
 'TEKNOVA|Discover the perfect setup|catalog-top|Laptops, Audio, Displays, Accessories|electronics,filters,topbar',
 'FORMA GOODS|Good design, made tangible|detail|Desk lamp, Brushed aluminum, Warm light, Durable|product,detail,product-gallery',
 'SUNDAY STUDIO|Objects worth keeping|editorial|Ceramics, Home ritual, Seasonal, Collectors|editorial,stories,grid',
 'FRESHLY MARKET|A better daily basket|metrics|Organic boxes, Local farms, Weekly offers, Delivery|market,statistics,subscription',
 'LUMEN SHOP|Design that works for you|form|Sign in, Email updates, Personal list, Membership|checkout,form,login',
 'PULSE CLUB|Find a plan for your routine|pricing|Starter, Member, Studio, Community|membership,pricing,cta',
 'WANDER CO|Every step tells a story|gallery|Trail shoes, Running gear, Travel packs, Clothing|gallery,filter,grid',
 'CROWN COLLECTION|From discovery to delivery|timeline|Discover, Personalize, Checkout, Delivery|ordering,steps,timeline',
 'ATLAS STORE|Shop what fits your space|table|Model, Dimensions, Finish, Availability|comparison,table,product',
 'MONO SUPPLY|Build your own set|article|Behind the craft, Materials, Sustainability, Workshop|journal,article,hero',
 'MERIDIAN SELLER|The store at a glance|dashboard|Revenue, Orders, Conversion, Active carts|seller,dashboard,chart',
],
'EDU': [
 'SKILLSPRING|Learn something meaningful|split|Design basics, Coding, Science, Writing|learning,courses,hero',
 'CAMPUS HUB|Find a course that fits|catalog-side|Web design, Data skills, UI foundations, Programming|course,filter,sidebar',
 'OPEN LEARN|Explore pathways at your pace|catalog-top|Short lessons, Guided labs, Workshops, Projects|learning-path,filter,grid',
 'MATH LAB|One concept at a time|detail|Geometry lesson, Video guide, Practice, Review|lesson,course,detail',
 'STUDY JOURNAL|Ideas grow through questions|editorial|Learning science, Study habits, Teaching, Student stories|journal,article,blog',
 'PROGRESS CAMPUS|See how far you have come|metrics|Completed units, Weekly hours, Current streak, Skills|student,statistics,chart',
 'MENTOR ROOM|Your next step starts here|form|Student email, Course code, Learning goals, Appointment|form,registration,contact',
 'ACADEMY PLUS|Choose your learning experience|pricing|Self-study, Mentored, Team, Institution|course,pricing,plans',
 'RESOURCE STUDIO|Learning by seeing|gallery|Diagrams, Interactive UI, Infographics, Worksheets|library,gallery,resources',
 'COURSE MAP|A clear path to mastery|timeline|Explore, Practice, Apply, Reflect|learning-path,timeline,progress',
 'CLASS SCHEDULE|Plan a better study week|table|Subject, Session, Instructor, Room|schedule,table,calendar',
 'RESEARCH CLASS|Discover the ideas behind it|article|Research methods, Evidence, Findings, Reflection|reading,article,research',
 'TEACHER PORTAL|Teaching, organized beautifully|dashboard|Active classes, Submissions, Engagement, Feedback|teacher,dashboard,analytics',
],
'BUS': [
 'NORTH CONSULT|Build what comes next|split|Advisory, Transformation, Research, Delivery|agency,services,hero',
 'KINFIELD GROUP|Solutions for every stage|catalog-side|Operations, Digital, People, Finance|consulting,sidebar,service-filter',
 'VERTEX PARTNERS|The right expertise in one place|catalog-top|Strategy, Design, Engineering, Support|professional,filter,grid',
 'STUDIO NORTH|A better way to work together|detail|Service brief, Project scope, Delivery, Outcomes|services,detail,case-study',
 'THE FIRM|Ideas with measurable impact|editorial|Perspectives, Research, Markets, People|corporate,journal,blog',
 'HORIZON CAPITAL|Performance in focus|metrics|Growth, Markets, Investments, Portfolio|finance,statistics,chart',
 'HELLO PARTNERS|Start the conversation|form|Full name, Work email, Request details, Meeting|contact,form,registration',
 'CLEARPATH|Straightforward service plans|pricing|Essential, Growth, Enterprise, Advisory|pricing,business,plans',
 'PROJECT INDEX|Work that moves ideas forward|gallery|Brand systems, Digital products, Campaigns, Strategy|portfolio,projects,grid',
 'IMPACT STUDIO|Progress is a process|timeline|Discover, Align, Build, Measure|process,timeline,steps',
 'EQUITY RESEARCH|See the complete picture|table|Market, Growth, Region, Outlook|corporate,table,comparison',
 'PEOPLE FIRST|Meet the people behind the work|article|Leadership, Culture, Our team, Values|team,careers,article',
 'OPERATIONS HQ|One view across the business|dashboard|Accounts, Projects, Team, Pipeline|crm,dashboard,analytics',
],
'NEW': [
 'THE CURRENT|Stories worth your attention|split|World, Culture, Science, Opinion|headlines,hero,news',
 'CITY DISPATCH|Explore the topics that matter|catalog-side|Local, Business, Environment, Community|topics,sidebar,filter',
 'DAILY REVIEW|A clearer view of the day|catalog-top|Politics, Technology, Culture, Design|headlines,top-filter,grid',
 'FIELD NOTES|Inside a remarkable idea|detail|Long read, Key points, Sources, Further reading|article,detail,reading',
 'MODERN JOURNAL|The stories behind the stories|editorial|Features, Essays, Interviews, Perspectives|magazine,editorial,grid',
 'DATA DESK|Beyond the headline|metrics|Readers, Articles, Topics, Engagement|journalism,statistics,chart',
 'THE LETTER|The week in your inbox|form|Email address, Areas of interest, Frequency, Subscribe|newsletter,subscription,form',
 'PAPER MEMBERSHIP|Choose how you read|pricing|Digital, Weekend, Archive, Patron|subscription,pricing,membership',
 'PHOTO ESSAYS|A collection of perspectives|gallery|Portraits, Landscapes, Events, Exhibits|photography,gallery,grid',
 'THE TIMELINE|Understanding the sequence|timeline|Background, Key moment, Response, Next|timeline,news,events',
 'MARKET WATCH|The figures behind the story|table|Sector, Change, Week, Signal|data,table,report',
 'SCIENCE REVIEW|Questions shape discovery|article|Research, Methods, Context, Evidence|science,article,research',
 'EDITOR DESK|Publishing at a glance|dashboard|Stories, Contributors, Engagement, Topics|editorial,dashboard,analytics',
],
'LAN': [
 'FLOWNOTE|Make ideas move forward|split|Capture notes, Organize work, Share updates, Stay focused|saas,product,hero',
 'EVENTFLOW|The conference starts here|catalog-side|Keynotes, Workshops, Speakers, Networking|events,sidebar,program',
 'WELLFORM|Healthy habits, simpler days|catalog-top|Movement, Nutrition, Sleep, Community|wellness,filter,grid',
 'PIXEL ONE|Made for your next big idea|detail|Product preview, Features, Compatibility, Early access|app,detail,product',
 'STORYFOUND|Every cause starts with a story|editorial|Mission, Impact, Stories, Community|nonprofit,stories,hero',
 'METRICA|Numbers you can actually use|metrics|Active users, Response time, Adoption, Growth|analytics,features,chart',
 'NEXT WAITLIST|Get early access today|form|Email address, Your role, Referral source, Join list|waitlist,form,cta',
 'LAUNCH LAB|Flexible plans for teams|pricing|Free, Standard, Pro, Enterprise|saas,pricing,subscription',
 'TRAVEL ECHO|A place worth discovering|gallery|City stays, Remote escapes, Food trails, Experiences|travel,gallery,grid',
 'STARTUP TRACK|From idea to launch|timeline|Discover, Prototype, Test, Launch|roadmap,timeline,steps',
 'COMPARE IT|Find the right workflow|table|Capability, Basic, Pro, Enterprise|comparison,table,features',
 'COURSE LAUNCH|A better way to learn design|article|Instructor, Outcomes, Curriculum, Testimonials|course,landing,article',
 'GROWTH PANEL|Your progress, in one view|dashboard|Signups, Adoption, Retention, Revenue|dashboard,saas,chart',
],
'DAS': [
 'ORBIT ANALYTICS|A clear view of performance|split|Overview, Activity, Insights, Reports|analytics,overview,hero',
 'CLIENTFLOW|Work with every account in one place|catalog-side|Prospects, Accounts, Contacts, Opportunities|crm,sidebar,filter',
 'TASKS STUDIO|Work planned, work delivered|catalog-top|Backlog, In progress, Review, Completed|project,kanban,filter',
 'STOCKWISE|Keep inventory under control|detail|Item details, Stock levels, Supplier, Reorder|inventory,details,product',
 'OPERATIONS JOURNAL|Understand every process|editorial|Incidents, Updates, Policies, Notes|operations,editorial,blog',
 'CASHFLOW HQ|The numbers behind decisions|metrics|Expenses, Cash flow, Invoices, Forecasts|finance,statistics,chart',
 'ACCOUNT CENTER|Set up your workspace|form|Workspace name, Team email, Timezone, Notifications|settings,form,login',
 'PLAN MANAGER|Choose a workspace plan|pricing|Solo, Team, Business, Enterprise|subscription,pricing,plans',
 'MEDIA LIBRARY|Your digital assets organized|gallery|Brand assets, Documents, Photography, Designs|assets,gallery,grid',
 'DELIVERY TRACKER|See every stage clearly|timeline|Requested, In progress, Review, Finished|project,timeline,workflow',
 'SUPPORT DESK|Keep requests on track|table|Ticket, Priority, Owner, Status|support,table,filter',
 'RESEARCH MONITOR|Explore the latest insights|article|Trends, Analysis, Notes, Highlights|reports,article,data',
 'TEAM PERFORMANCE|Make progress visible|dashboard|Open tasks, Completed, Velocity, Team load|team,analytics,dashboard',
]
}
KIND_COMPONENTS = {
 'split':['navbar','hero','cta','cards'], 'catalog-side':['navbar','sidebar','filter','grid','cards','search'],
 'catalog-top':['navbar','filter','grid','cards','search'], 'detail':['navbar','product','cards','cta'],
 'editorial':['navbar','hero','article','cards','grid'], 'metrics':['navbar','statistics','chart','cards'],
 'form':['navbar','hero','form','cta'], 'pricing':['navbar','pricing','cards','cta'],
 'gallery':['navbar','grid','cards','filter'], 'timeline':['navbar','cards'],
 'table':['navbar','dashboard','filter'], 'article':['navbar','hero','article'],
 'dashboard':['navbar','sidebar','dashboard','chart','statistics','cards'],
}
RELATIONS = {
 'catalog-side':[{'subject':'sidebar','predicate':'left_of','object':'grid'},{'subject':'filter','predicate':'inside','object':'sidebar'}],
 'catalog-top':[{'subject':'filter','predicate':'above','object':'grid'}],
 'metrics':[{'subject':'statistics','predicate':'above','object':'chart'}],
 'dashboard':[{'subject':'sidebar','predicate':'left_of','object':'chart'},{'subject':'statistics','predicate':'above','object':'chart'}],
 'form':[{'subject':'form','predicate':'right_of','object':'hero'}],
}


def esc(v): return html.escape(str(v),quote=True)
def stars(items): return ''.join(f'<span class="chip">{esc(x)}</span>' for x in items)
def panel_art(idx,subjects):
    return f'<div class="abstract-art art-{idx%5}"><div class="orb orb-a"></div><div class="orb orb-b"></div><div class="art-window"><span class="art-top">BROWSE / EXPLORE</span><strong>{esc(subjects[idx%len(subjects)])}</strong><span>Designed for clarity</span></div></div>'

def product_cards(labels,count=6,klass='catalog-grid'):
    cards=[]
    for j in range(count):
        label=esc(labels[j%len(labels)])
        cards.append(f'<article class="product-card"><div class="product-picture pic-{j%6}"><div class="product-symbol">{(j+1):02d}</div></div><div class="product-copy"><strong>{label}</strong><span>Explore collection</span><b>{j+1:02d} / EDIT</b></div></article>')
    return f'<div class="{klass}">'+''.join(cards)+'</div>'

def tiles(labels,count=4):
    return '<div class="feature-tiles">'+''.join(f'<div class="feature-tile"><span class="tile-number">0{j+1}</span><strong>{esc(s)}</strong><p>Browse ideas and discover practical examples for this area.</p><span class="tile-arrow">Explore &rarr;</span></div>' for j,s in enumerate(labels[:count]))+'</div>'

def chart():
    columns=[43,67,49,81,65,91,72,97,83,100,87,106]
    return '<div class="chart-box"><div class="chart-head"><span>Performance overview</span><b>Last 12 periods</b></div><div class="chart-bars">'+''.join(f'<div class="bar" style="height:{v}%"><span>{str(i+1).zfill(2)}</span></div>' for i,v in enumerate(columns))+'</div></div>'

def table(labels):
    headers=['Item','Segment','Owner','Status']
    out='<table class="data-table"><thead><tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr></thead><tbody>'
    for i,s in enumerate(labels*2):
        if i>=7:break
        out+=f'<tr><td><b>{esc(s)}</b></td><td>{["Design","Services","Research","Operations"][i%4]}</td><td>Team {i%4+1:02d}</td><td><span class="state state-{i%3}">{["Active","Planned","Review"][i%3]}</span></td></tr>'
    return out+'</tbody></table>'


def build_content(kind,spec,i):
    labels=spec['labels']; title=esc(spec['title']); cat=esc(spec['category_vi']);
    buttons='<a class="button primary" href="#explore">Explore collection <span>&rarr;</span></a><a class="button button-ghost" href="#about">Learn more</a>'
    eyebrow=f'<span class="eyebrow"><i></i>{cat} <span class="slash">/</span> Interface {i:02d}</span>'
    focus=', '.join(labels[:3])
    p=f'<p class="lead">Explore {esc(focus)} through a {esc(kind.replace("-"," "))} interface. This learning example demonstrates content hierarchy, practical components and purposeful navigation.</p>'
    if kind=='split':
        return f'<section class="hero hero-split"><div>{eyebrow}<h1>{title}</h1>{p}<div class="actions">{buttons}</div></div>{panel_art(i,labels)}</section><section id="explore" class="section"><div class="section-head"><div><span class="overline">CURATED AREAS</span><h2>Start exploring</h2></div><span class="section-aside">Discover what matters</span></div>{tiles(labels)}</section>'
    if kind=='catalog-side':
        return f'<section class="section heading-row">{eyebrow}<h1>{title}</h1>{p}</section><section id="explore" class="section catalogue-with-sidebar"><aside class="filter-panel"><h3>Refine results</h3><div class="search-input">Search collections...</div><div class="filter-label">Categories</div>'+''.join(f'<label class="checkbox-line"><input type="checkbox" {"checked" if j==0 else ""}> {esc(x)}</label>' for j,x in enumerate(labels))+f'<div class="filter-label">Availability</div><div class="checkbox-line">&#9673; Ready to explore</div><div class="filter-label">Style</div><div class="range-bar"></div></aside><div class="catalog-body"><div class="section-head small"><div><span class="overline">SELECTED COLLECTION</span><h2>Browse everything</h2></div><span class="section-aside">Sort by: Featured &darr;</span></div>{product_cards(labels)}</div></section>'
    if kind=='catalog-top':
        return f'<section class="section heading-row compact">{eyebrow}<h1>{title}</h1>{p}</section><section id="explore" class="section"><div class="horizontal-filter"><div class="filter-caption">Browse by category</div>{stars(["All"]+labels)}<span class="sort-ctrl">Sort: Featured &darr;</span></div><div class="section-head small"><h2>Recommended for you</h2><span class="section-aside">{len(labels)*5} ideas</span></div>{product_cards(labels,8)}</section>'
    if kind=='detail':
        return f'<section class="section detail-layout" id="explore"><div class="detail-visual">{panel_art(i,labels)}<div class="thumbnail-strip">'+''.join(f'<span class="thumbnail tiny-{k}"></span>' for k in range(4))+f'</div></div><div class="detail-copy">{eyebrow}<h1>{title}</h1><div class="tag-row">{stars(labels[:3])}</div>{p}<div class="detail-list"><div><b>Thoughtfully designed</b><span>Clear structure and readable components</span></div><div><b>Practical patterns</b><span>Reusable approach across screen sizes</span></div><div><b>Focused experience</b><span>Built around user needs</span></div></div><div class="actions">{buttons}</div></div></section><section class="section"><h2>Explore related ideas</h2>{tiles(labels)}</section>'
    if kind=='editorial':
        return f'<section class="section editorial-mast"><div>{eyebrow}<h1>{title}</h1>{p}</div><div class="edition">ISSUE <strong>{i:02d}</strong><span>Features and perspectives</span></div></section><section class="section editorial-feature" id="explore"><div class="editorial-main">{panel_art(i,labels)}<div class="article-head"><span class="overline">FEATURE STORY</span><h2>{esc(labels[0])}: a fresh perspective</h2><p>An editorial look at the details and decisions that make a difference.</p></div></div><div class="editorial-side">'+''.join(f'<article><span class="overline">{j+1:02d} / INSIGHTS</span><h3>{esc(v)}</h3><p>Understanding patterns in practice.</p></article>' for j,v in enumerate(labels[1:]))+'</div></section>'
    if kind=='metrics':
        numbers=['24.8k','86%','12.4k','+18.6%']
        summary=''.join(f'<div class="metric-card"><span>{esc(s)}</span><strong>{numbers[j%4]}</strong><small>+{j*3+4}.2% this period</small></div>' for j,s in enumerate(labels[:4]))
        return f'<section class="section heading-row compact">{eyebrow}<h1>{title}</h1>{p}</section><section class="section dashboard-summary" id="explore"><div class="metrics-row">{summary}</div><div class="metrics-content">{chart()}<div class="insights-pane"><h2>Highlights</h2><p>Key signals from the selected period.</p>'+''.join(f'<div><strong>{esc(s)}</strong><span>Meaningful change across key indicators.</span></div>' for s in labels[:3])+'</div></div></section>'
    if kind=='form':
        fields=[('Full name','Enter your name'),('Email address','name@example.com'),('Area of interest','Select an option'),('Your message','Tell us what you need')]
        form=''.join(f'<label><span>{t}</span><input type="text" aria-label="{t}" placeholder="{v}"></label>' for t,v in fields)
        return f'<section class="section signup-layout" id="explore"><div class="signup-copy">{eyebrow}<h1>{title}</h1>{p}{panel_art(i,labels)}</div><div class="signup-card"><span class="overline">GET IN TOUCH</span><h2>Make your next move</h2><p>Example input form for learning interface structure.</p><form onsubmit="return false">{form}<label class="agree-line"><input type="checkbox"> I agree to the demo terms</label><button class="button primary" type="button">Submit preview &rarr;</button></form><small>Demonstration only; information is not submitted.</small></div></section>'
    if kind=='pricing':
        names=['Starter','Growth','Advanced']
        prices=['Free','$18','$42']
        cs=[]
        for j in range(3):
            feat=''.join(f'<li>{esc(labels[(j+k)%len(labels)])}</li>' for k in range(4))
            cs.append(f'<article class="plan {"plan-featured" if j==1 else ""}"><span class="overline">{names[j].upper()}</span><h2>{prices[j]} <small>/month</small></h2><p>A practical package for {names[j].lower()} needs.</p><ul>{feat}</ul><a href="#explore" class="button {"primary" if j==1 else "button-ghost"}">Explore plan &rarr;</a></article>')
        return f'<section class="section centered-header">{eyebrow}<h1>{title}</h1>{p}</section><section class="section pricing-grid" id="explore">'+''.join(cs)+'</section>'
    if kind=='gallery':
        return f'<section class="section heading-row">{eyebrow}<h1>{title}</h1>{p}</section><section id="explore" class="section"><div class="horizontal-filter"><span class="filter-caption">Explore by theme</span>{stars(["Featured"]+labels)}</div>{product_cards(labels,8,"gallery-grid")}</section>'
    if kind=='timeline':
        steps=['Discover','Plan','Build','Review']
        nodes=''.join(f'<div class="time-node"><div class="time-dot">{j+1:02d}</div><span class="overline">PHASE {j+1}</span><h3>{esc(steps[j])}</h3><p>{esc(labels[j%len(labels)])}: follow the essentials through every phase.</p></div>' for j in range(4))
        return f'<section class="section centered-header">{eyebrow}<h1>{title}</h1>{p}</section><section id="explore" class="section"><h2>A clear path forward</h2><div class="timeline-row">{nodes}</div><div class="timeline-bottom"><div><span class="overline">WHAT COMES NEXT</span><h2>Every step builds confidence</h2><p>See how each stage contributes to a thoughtful result.</p></div>{panel_art(i,labels)}</div></section>'
    if kind=='table':
        return f'<section class="section heading-row compact">{eyebrow}<h1>{title}</h1>{p}</section><section class="section data-workspace" id="explore"><div class="data-toolbar"><div><span class="overline">COMPARISON VIEW</span><h2>All in one place</h2></div><span class="search-input">Search records...</span><button class="button button-ghost" type="button">Export preview</button></div>{table(labels)}<p class="table-note">Illustrative sample records for layout practice. No real data is used.</p></section>'
    if kind=='article':
        return f'<section class="section article-layout" id="explore"><article class="long-read">{eyebrow}<h1>{title}</h1><p class="article-intro">The ideas behind better digital experiences and how small details shape the bigger picture.</p><div class="byline"><span class="avatar">UI</span><span>Editorial Studio<br><small>Updated November 2026</small></span></div>{panel_art(i,labels)}<h2>Design begins with a clear purpose</h2><p>Well-designed interfaces connect information with action. A clear hierarchy, meaningful spacing and carefully chosen components help people understand where to go next.</p><h2>From patterns to practice</h2><p>By analyzing examples, designers can compare solutions and select structures that match a specific user need. The sample demonstrates typography, article content and visual rhythm.</p></article><aside class="toc"><b>ON THIS PAGE</b><p>Overview</p><p>Design principles</p><p>Examples</p><p>Further reading</p><hr><span>READ TIME: 4 MIN</span></aside></section>'
    if kind=='dashboard':
        sums=''.join(f'<div class="metric-card"><span>{esc(s)}</span><strong>{["5,240","84.6%","1,382","+21%"][j%4]}</strong><small>Updated today</small></div>' for j,s in enumerate(labels[:4]))
        side=''.join(f'<div class="side-item {"active" if j==0 else ""}"><span class="side-dot"></span>{esc(s)}</div>' for j,s in enumerate(labels))
        return f'<section class="app-dashboard" id="explore"><aside class="app-sidebar"><strong>Workspace</strong><span class="overline">NAVIGATION</span>{side}<div class="sidebar-foot">System overview<br><small>Demo workspace</small></div></aside><div class="workspace-main"><div class="workspace-top"><div>{eyebrow}<h1>{title}</h1></div><span class="pill">Last 30 days &darr;</span></div><div class="metrics-row">{sums}</div><div class="metrics-content">{chart()}<div class="insights-pane"><h2>Latest activity</h2>'+''.join(f'<div><strong>{esc(s)}</strong><span>Updated status and key highlights.</span></div>' for s in labels[:4])+f'</div></div><div class="table-wrap"><h2>Recent records</h2>{table(labels)}</div></div></section>'
    raise ValueError(kind)


def render_page(spec):
    # Pages reference a single shared stylesheet for maintainability.
    i=spec['n']; acc=spec['accent']; shade=spec['shade']; brand=esc(spec['brand'])
    labels=spec['labels']; nav=''.join(f'<a href="#explore">{esc(t)}</a>' for t in labels[:3]);
    content=build_content(spec['kind'],spec,i)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Web UI learning sample {spec['id']}. Original HTML/CSS layout for education.">
<title>{brand} - {esc(spec['title'])} - Web UI Sample</title>
<link rel="stylesheet" href="../assets/sample-150.css">
<style>:root{{--accent:{acc};--soft:{shade};--shift:{(i*19)%360}deg}}</style>
</head><body class="type-{spec['kind']} group-{spec['prefix'].lower()}">
<div class="page-shell"><header class="site-nav"><a class="brand" href="#top"><span class="brand-mark">{brand[:1].upper()}</span>{brand}</a><nav>{nav}</nav><div class="nav-utilities"><span class="nav-magnifier" aria-label="Search demonstration">&#9906;</span><a class="nav-action" href="#explore">Explore <span>&rarr;</span></a></div></header>
<main id="top">{content}</main>
<footer class="footer"><div><strong>{brand}</strong><span>Original interface learning example &middot; {esc(spec['category_vi'])}</span></div><div><span>Sample {spec['id']}</span><span>UI demonstration, not a commercial service</span></div></footer></div>
</body></html>'''


def all_specs():
    rows=[]
    for prefix,raws in RAW.items():
        group, vi, colors, shades, _ = GROUPS[prefix]
        if len(raws)!=13: raise AssertionError(f'{prefix} has {len(raws)} instead of 13')
        for offset,row in enumerate(raws):
            brand,title,kind,labels,tags=row.split('|')
            n=13+offset
            components=KIND_COMPONENTS[kind]
            extras=[x.strip() for x in tags.split(',') if x.strip()]
            spec={'id':f'WEB-{prefix}-{n:03d}', 'prefix':prefix, 'n':n,
                  'brand':brand,'title':title,'kind':kind,'labels':[x.strip() for x in labels.split(',')],
                  'category':group,'category_vi':vi,'accent':colors[offset%4], 'shade':shades[offset%4],
                  'components':components,'tags':list(dict.fromkeys([vi,group]+components+extras)),
                  'relations':RELATIONS.get(kind,[])}
            rows.append(spec)
    return rows


def build_catalog_and_fallback(specs):
    catalog_file=ROOT/'data/catalog.yaml'
    data=yaml.safe_load(catalog_file.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):raise ValueError('Invalid catalog.yaml')
    existing=data['items']; exist={r['id']:r for r in existing}
    if len(existing)<72:raise ValueError('Existing catalog missing original entries')
    assert {f'WEB-{p}-{i:03d}' for p in GROUPS for i in range(1,13)}.issubset(exist), 'Original 72 IDs missing'
    for spec in specs:
        id=spec['id']
        if id in exist:
            if exist[id].get('source')!='synthetic_gallery_extension_150':
                raise ValueError(f'Collision with manually edited item {id}. Will not overwrite.')
            # Generator-owned rows may be refreshed; retain their creation timestamp.
            exist[id].update({'description':f"Web UI practice: {spec['category_vi']}. {spec['title']}. Layout {spec['kind']}; key parts: {', '.join(spec['components'])}.",
                'tags':spec['tags'],'category':spec['category'],'components':spec['components'],
                'layout':spec['kind'],'relations':spec['relations']})
            continue
        title=spec['title']
        record={
            'id':id, 'page_url':f'{BASE}/pages/{id}.html', 'title':title,
            'description':f"Web UI practice: {spec['category_vi']}. {title}. Layout {spec['kind']}; key parts: {', '.join(spec['components'])}.",
            'tags':spec['tags'], 'category':spec['category'], 'components':spec['components'],
            'layout':spec['kind'], 'relations':spec['relations'],
            'source':'synthetic_gallery_extension_150', 'verified':False,
            'created_at':STAMP,'updated_at':STAMP}
        existing.append(record)
    order={name:i for i,name in enumerate(GROUPS)}
    data['items']=sorted(existing,key=lambda x:(order.get(x['id'].split('-')[1],99),int(x['id'].split('-')[-1])))
    counts=Counter(r['id'].split('-')[1] for r in data['items'] if re.fullmatch(r'WEB-[A-Z]{3}-\d{3}',str(r.get('id',''))))
    if len(data['items'])!=150 or any(counts.get(k)!=25 for k in GROUPS):
        raise AssertionError(f'Expected 150 samples with 25 per group, got {len(data["items"])} {counts}')
    catalog_file.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False,width=115),encoding='utf-8')
    fallback_file=DOCS/'gallery-fallback.json'
    before=json.loads(fallback_file.read_text(encoding='utf-8'))
    by_id={r['id']:r for r in before}
    for spec in specs:
        id=spec['id']
        if id in by_id:continue
        by_id[id]={'id':id,'title':spec['title'],
                   'description':f"{spec['brand']}: {spec['title']}. {spec['category_vi']}; {spec['kind']}; {', '.join(spec['components'])}.",
                   'category':spec['category'],'tags':spec['tags'],
                   'page_url':f'{BASE}/pages/{id}.html','local_preview':f'previews/{id}.webp'}
    fallback=sorted(by_id.values(),key=lambda x:(order.get(x['id'].split('-')[1],99),int(x['id'].split('-')[-1])))
    assert len(fallback)==150
    fallback_file.write_text(json.dumps(fallback,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return counts



def update_links_and_existing_tests():
    # These surgical edits preserve optional assessment links or later site changes.
    index=DOCS/'index.html'
    content=index.read_text(encoding='utf-8')
    if 'huong-dan.html' not in content:
        before='<a href="#gioi-thieu">Giới thiệu</a>'
        # Browser source is UTF-8. Reconstructed literal avoids shell Unicode.
        if before in content:
            content=content.replace(before,before+'\n        <a href="huong-dan.html">Hướng dẫn</a>',1)
        else:
            content=content.replace('</nav>','<a href="huong-dan.html">Hướng dẫn</a></nav>',1)
    content=content.replace('id="resourcesCount">72<','id="resourcesCount">150<')
    index.write_text(content,encoding='utf-8')
    # The legacy test suite asserted the old teaching set size of 72.
    for testfile in [ROOT/'tests/test_app.py',ROOT/'tests/test_pages_cors.py']:
        if testfile.is_file():
            text=testfile.read_text(encoding='utf-8')
            if '==72' in text:
                testfile.write_text(text.replace('==72','==150'),encoding='utf-8')
    # Pre-existing seed script would discard all 78 additions; block its use.
    seedfile=ROOT/'scripts/seed_catalog.py'
    if seedfile.is_file():
        content=seedfile.read_text(encoding='utf-8')
        guard='if output.exists():\n    raise SystemExit("Catalog already exists. Do not overwrite the 150-sample collection with the 72-sample seed.")\n'
        marker="output.parent.mkdir(exist_ok=True,parents=True)\n"
        if 'Do not overwrite the 150-sample collection' not in content and marker in content:
            content=content.replace(marker,marker+guard)
            seedfile.write_text(content,encoding='utf-8')
    # Keep README version-agnostic and append how-to link without duplication.
    readme=ROOT/'README.md'
    if readme.is_file():
        content=readme.read_text(encoding='utf-8')
        if '## Kho hoc lieu 150 mau' not in content:
            content+='\n\n## Kho hoc lieu 150 mau\n\n- 6 nhom x 25 mau, giu nguyen 72 mau goc.\n- 78 mau moi: `docs/pages/WEB-XXX-013.html` den `WEB-XXX-025.html`.\n- Anh xem truoc: `docs/previews/`; metadata: `data/catalog.yaml`.\n- Huong dan su dung: `https://hcmue.github.io/lokg-web-gallery/huong-dan.html`.\n- Khi sua YAML tren GitHub, Render can deploy lai hoac admin nhan tai lai du lieu.\n'
            readme.write_text(content,encoding='utf-8')


def main():
    specs=all_specs()
    pages=DOCS/'pages'; pages.mkdir(exist_ok=True,parents=True)
    for spec in specs:
        dest=pages/(spec['id']+'.html')
        # Generated pages may be rebuilt; never overwrite original 001-012.
        dest.write_text(render_page(spec),encoding='utf-8')
    counts=build_catalog_and_fallback(specs)
    update_links_and_existing_tests()
    print(f'New pages: {len(specs)}; total catalog: {sum(counts.values())}; each group: {dict(counts)}')
    print('Next: python scripts/render_150_previews.py (requires Chromium + Playwright + Pillow)')

if __name__=='__main__':main()
