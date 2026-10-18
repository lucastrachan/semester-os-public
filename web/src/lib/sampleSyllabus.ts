// A clearly fictional syllabus for demos ("Try with a sample syllabus"). Dates are generated from today so the
// extracted deadlines always land in the near future. Contains no real school, person, email or phone number.
const fmt = (d: Date) => d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
const plus = (days: number) => { const d = new Date(); d.setDate(d.getDate() + days); return d }

export function sampleSyllabus(): string {
  const start = plus(-14), end = plus(100)
  return `SAMPLE COURSE (FICTIONAL, for demos only): not a real class
DEMO 101: Introduction to Studying Smarter
Term: Demo Term. Classes run ${fmt(start)} through ${fmt(end)}.
Instructor: Dr. Alex Example. Office hours: Tuesdays 2:00-3:30 PM, Example Hall room 100.
Meets: Monday and Wednesday, 10:00-10:50 AM, Example Hall room 101.

Course description
A short introduction to evidence-based study habits: spaced practice, retrieval practice, planning and reflection. This syllabus is made up so you can try Semester OS without uploading anything real.

Required book
Studying Smarter: A Fictional Guide, 2nd edition, by Pat Placeholder (Example Press). Required.
Optional: The Demo Workbook, 1st edition, by Pat Placeholder. Optional.

Grading
Quizzes 20%. Midterm exam 25%. Study journal 15%. Research paper 15%. Final exam 25%.

Schedule and deadlines
- Quiz 1: ${fmt(plus(8))}, 10:00 AM, in class.
- Study journal check-in 1: due ${fmt(plus(12))} at 11:59 PM.
- Midterm exam: ${fmt(plus(21))}, 10:00 AM, in class.
- Research paper: due ${fmt(plus(35))} at 11:59 PM.
- Quiz 2: ${fmt(plus(45))}, 10:00 AM, in class.
- Final exam: ${fmt(plus(60))}, 10:00 AM, Example Hall room 101.

Policies
Late work: lose 10% per day, up to three days. Attendance: encouraged, not graded. AI tools: allowed for explaining concepts and quizzing yourself; not allowed to write graded work. Other: collaboration is welcome on the study journal, but write your own answers.`
}
