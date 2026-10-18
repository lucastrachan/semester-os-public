import re, pathlib
here = pathlib.Path(__file__).parent
p = here / 'template.html'
t = p.read_text(encoding='utf-8')
n0 = len(re.findall(r'\[\[BB:', t))
rules = [
 ('[[BB:Upload your syllabi|Connect Blackboard]]. Get an AI agent', 'Add your syllabi and connect your Blackboard calendar. Get an AI agent'),
 ('[[BB:Drop the syllabi, once|Connect Blackboard once]]', 'Syllabi add classes, Blackboard adds deadlines'),
 ('[[BB:Syllabus|Blackboard]]<small>[[BB:you upload it|connect and import your classes]]</small>', 'Syllabus<small>adds a class; your Blackboard calendar pulls in every deadline</small>'),
 ('[[BB:Sign up, drop a syllabus, the agent builds itself|Sign up, connect Blackboard, your classes build themselves]]', 'Sign up, add a class by syllabus, the agent builds itself'),
 ('[[BB:Drop a syllabus PDF here to add a class|Connect Blackboard to import your classes]]', 'Add a class by syllabus, or connect your Blackboard calendar to pull in every deadline'),
 ('[[BB:Upload|Connect]]', 'Add'),
 ('Canvas scan, browser extension, listing photos', 'Canvas scan, guided browser extension (prototype), listing photos'),
 ('<span class="pill">Browser extension</span>', '<span class="pill">Browser helper (prototype)</span>'),
 ('Next (roadmap): Canvas and Blackboard connect, browser extension, listing photos.', 'Next (roadmap): Canvas connect, guided browser extension (prototype), listing photos.'),
]
for a, b in rules:
    if a in t:
        t = t.replace(a, b)
    else:
        print('MISSING', a[:50])
print('left BB markers:', len(re.findall(r'\[\[BB:', t)), 'of', n0)
p.write_text(t, encoding='utf-8')
