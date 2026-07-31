import os
import re

css_path = r'c:\Users\HUAWEI\Desktop\jodah\static\css\admin_custom.css'
with open(css_path, 'r', encoding='utf-8') as f:
    css = f.read()

# 1. Variables and imports
css = css.replace(
    ':root {',
    "@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');\n\n:root {"
)

css = css.replace('--jm-navy: #0d1b2e;', '--jm-navy: #050B14;')
css = css.replace('--jm-navy2: #112240;', '--jm-navy2: #0A142A;')
css = css.replace('--jm-navy3: #162d4a;', '--jm-navy3: #0F1D36;')
css = css.replace('--jm-gold: #c5a059;', '--jm-gold: #d4af37;')
css = css.replace('--jm-gold-h: #d4b06e;', '--jm-gold-h: #f3e5ab;')
css = css.replace('--jm-border: rgba(197, 160, 89, 0.18);', '--jm-border: rgba(255, 255, 255, 0.15);')

# 2. Body background
old_body = """body,
.wrapper,
.content-wrapper {
    background: #0f1923 !important;
    color: #e2e8f0 !important;
}"""
new_body = """body,
.wrapper,
.content-wrapper {
    background-color: var(--jm-navy) !important;
    background-image: 
        radial-gradient(circle at 15% 25%, rgba(212, 175, 55, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 75% 85%, rgba(212, 175, 55, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 80% 20%, rgba(212, 175, 55, 0.05) 0%, transparent 30%) !important;
    color: var(--jm-white) !important;
    font-family: 'Cairo', sans-serif !important;
}"""
css = css.replace(old_body, new_body)

# 3. Search box
old_search = """/* Search box */
.main-header .form-control {
    background: var(--jm-navy3) !important;
    border: 1px solid var(--jm-border) !important;
    color: #e2e8f0 !important;
}"""
new_search = """/* Search box */
.main-header .form-control {
    background: rgba(10, 20, 42, 0.6) !important;
    border: 1px solid rgba(212, 175, 55, 0.6) !important;
    box-shadow: 0 0 8px rgba(212, 175, 55, 0.2);
    color: var(--jm-white) !important;
}
.main-header .form-control:focus {
    border-color: var(--jm-gold) !important;
    box-shadow: 0 0 12px rgba(212, 175, 55, 0.4) !important;
}"""
css = css.replace(old_search, new_search)

# 4. Sidebar
old_sidebar = """.main-sidebar,
.main-sidebar .sidebar {
    background: var(--jm-navy) !important;
    border-right: 1px solid var(--jm-border) !important;
}"""
new_sidebar = """.main-sidebar,
.main-sidebar .sidebar {
    background: rgba(10, 20, 42, 0.4) !important;
    backdrop-filter: blur(15px);
    border-right: 1px solid var(--jm-border) !important;
}"""
css = css.replace(old_sidebar, new_sidebar)

css = css.replace("background: var(--jm-navy) !important;\n    border-bottom: 1px solid var(--jm-border) !important;\n    padding: 14px 16px !important;", "background: transparent !important;\n    border-bottom: 1px solid var(--jm-border) !important;\n    padding: 14px 16px !important;")

# Sidebar items color
css = css.replace("color: #b0bec5 !important;", "color: var(--jm-white) !important;")
css = css.replace("background: rgba(197, 160, 89, 0.1) !important;\n    color: var(--jm-gold) !important;\n    border-right: 3px solid var(--jm-gold) !important;", "background: rgba(255, 255, 255, 0.1) !important;\n    color: var(--jm-white) !important;\n    border-right: 3px solid var(--jm-white) !important;")
css = css.replace("background: rgba(197, 160, 89, 0.14) !important;\n    color: var(--jm-gold) !important;\n    font-weight: 700 !important;\n    border-right: 3px solid var(--jm-gold) !important;", "background: var(--jm-white) !important;\n    color: var(--jm-navy) !important;\n    font-weight: 800 !important;\n    border: 1px solid var(--jm-gold) !important;\n    border-right: 1px solid var(--jm-gold) !important;")

css = css.replace("color: var(--jm-gold) !important;\n    opacity: 0.85;\n    width: 1.4em;", "color: var(--jm-white) !important;\n    opacity: 1;\n    width: 1.4em;\n}\n\n.nav-sidebar .nav-item>.nav-link.active i,\n.nav-sidebar .nav-item.menu-open>.nav-link i {\n    color: var(--jm-gold) !important;")

# Remove red
css = css.replace('#dc2626', '#b45309')
css = css.replace('#ef4444', '#b45309')
css = css.replace('#f87171', '#fcd34d')

# KPI Cards
old_kpi = """.jm-kpi-card {
    background: linear-gradient(135deg, var(--jm-navy2), var(--jm-navy3));
    border: 1px solid var(--jm-border);
    border-radius: 14px;
    padding: 22px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: 0.3s;
    position: relative;
    overflow: hidden;
    cursor: default;
}

.jm-kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    border-color: rgba(197, 160, 89, 0.4);
}

.jm-kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    right: 0;
    width: 3px;
    height: 100%;
    background: var(--jm-gold);
    border-radius: 0 14px 14px 0;
}

.jm-kpi-icon {
    width: 50px;
    height: 50px;
    border-radius: 12px;
    background: rgba(197, 160, 89, 0.12);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
    color: var(--jm-gold);
    flex-shrink: 0;
}

.jm-kpi-value {
    font-size: 2rem;
    font-weight: 800;
    color: var(--jm-white);
    line-height: 1;
    font-variant-numeric: tabular-nums;
}"""
new_kpi = """.jm-kpi-card {
    background: rgba(10, 20, 42, 0.4) !important;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 14px;
    padding: 22px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: 0.3s;
    position: relative;
    overflow: hidden;
    cursor: default;
    box-shadow: 0 0 15px rgba(255, 255, 255, 0.05), inset 0 0 20px rgba(255, 255, 255, 0.02) !important;
}

.jm-kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 0 25px rgba(212, 175, 55, 0.15), inset 0 0 20px rgba(255, 255, 255, 0.05) !important;
    border-color: rgba(255, 255, 255, 0.3) !important;
}

.jm-kpi-card::before {
    display: none;
}

.jm-kpi-icon {
    width: 50px;
    height: 50px;
    border-radius: 12px;
    background: transparent;
    border: 1px solid rgba(212, 175, 55, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    color: var(--jm-gold);
    box-shadow: 0 0 15px rgba(212, 175, 55, 0.2), inset 0 0 10px rgba(212, 175, 55, 0.1);
    flex-shrink: 0;
}

.jm-kpi-value {
    font-size: 2.2rem;
    font-weight: 800;
    color: var(--jm-gold);
    text-shadow: 0 0 10px rgba(212, 175, 55, 0.3);
    line-height: 1;
    font-variant-numeric: tabular-nums;
}"""
css = css.replace(old_kpi, new_kpi)

css = css.replace("""/* Dashboard greeting */
.jm-greeting {
    color: #e2e8f0;""", """/* Dashboard greeting */
.jm-greeting {
    color: var(--jm-white);""")
css = css.replace(""".jm-greeting span {
    color: var(--jm-gold);""", """.jm-greeting span {
    color: var(--jm-white);""")
css = css.replace(""".jm-datetime {
    color: #64748b;""", """.jm-datetime {
    color: var(--jm-white);
    opacity: 0.9;""")

css = css.replace(""".jm-notif-text {
    font-size: 0.88rem;
    color: #e2e8f0;""", """.jm-notif-text {
    font-size: 0.88rem;
    color: var(--jm-white);""")
css = css.replace(""".jm-notif-sub {
    font-size: 0.76rem;
    color: var(--jm-muted);""", """.jm-notif-sub {
    font-size: 0.76rem;
    color: var(--jm-white);
    opacity: 0.9;""")

# Status badge
css = css.replace(""".jm-status-badge {
    color: #fff;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.68rem;
    font-weight: 700;
    white-space: nowrap;
}""", """.jm-status-badge {
    color: var(--jm-navy);
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.68rem;
    font-weight: 800;
    white-space: nowrap;
    box-shadow: 0 0 10px currentColor;
}""")

with open(css_path, 'w', encoding='utf-8') as f:
    f.write(css)

# Update index.html
html_path = r'c:\Users\HUAWEI\Desktop\jodah\templates\admin\index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace(
    '<h1 style="color:#c5a059;font-weight:800;font-size:1.6rem;margin:0;">',
    '<h1 style="color:#d4af37;text-shadow:0 0 10px rgba(212,175,55,0.4);font-weight:800;font-size:1.6rem;margin:0;">'
)
html = html.replace(
    '<i class="fas fa-th-large" style="margin-left:8px;font-size:1.2rem;"></i>',
    '<i class="fas fa-th-large" style="margin-left:8px;font-size:1.2rem;color:#d4af37;"></i>'
)

# Glow status
html = html.replace(
    "const map = { new: ['جديد', '#3b82f6'], matched: ['مطابَق', '#22c55e'], contacted: ['تم التواصل', '#a855f7'], closed: ['مغلق', '#64748b'] };",
    "const map = { new: ['جديد', '#facc15'], matched: ['مطابَق', '#4ade80'], contacted: ['تم التواصل', '#c084fc'], closed: ['مغلق', '#94a3b8'] };"
)

# List dots
old_dot_req = """<div class="jm-notif-dot2" style="background:rgba(59,130,246,0.12);color:#60a5fa;">
                        <i class="fas fa-user"></i>
                    </div>"""
new_dot_req = """<div class="jm-notif-dot2" style="background:rgba(255,255,255,0.05);color:#ffffff;border:1px solid rgba(255,255,255,0.2);box-shadow:inset 0 0 5px rgba(212,175,55,0.2);">
                        <i class="fas fa-user" style="text-shadow:0 0 5px rgba(212,175,55,0.5);"></i>
                    </div>"""
html = html.replace(old_dot_req, new_dot_req)

old_dot_off = """<div class="jm-notif-dot2" style="background:rgba(197,160,89,0.12);color:#c5a059;">
                        <i class="fas fa-home"></i>
                    </div>"""
new_dot_off = """<div class="jm-notif-dot2" style="background:rgba(255,255,255,0.05);color:#ffffff;border:1px solid rgba(255,255,255,0.2);box-shadow:inset 0 0 5px rgba(212,175,55,0.2);">
                        <i class="fas fa-home" style="text-shadow:0 0 5px rgba(212,175,55,0.5);"></i>
                    </div>"""
html = html.replace(old_dot_off, new_dot_off)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
