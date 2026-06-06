# UI Flow Storyboard

Frame files are local-only evidence references and may contain PHI-like chart data. They are ignored by `.gitignore`.

| Time | Capture | Screen / action | Notes |
|---|---|---|---|
| 00:00 | `captures/phrase-01-000s.png` | Client Overview | Admission date and current LOC visible on client overview; left sidebar and top utility bar establish app style. |
| 00:06 | `captures/phrase-02-006s.png` | Navigate to Treatment Plan tab | Presenter moves from overview toward Treatment Plan. |
| 00:16 | `captures/phrase-03-016s.png` | Treatment Plan tab, plan/version grid | Top grid includes plan summary. Lower grid includes version rows for MTP and Initial. |
| 00:28 | `captures/phrase-04-028s.png` | Initial Treatment Plan modal, signature area | Client and staff signatures are checked against admission date. |
| 00:34 | `captures/phrase-05-034s.png` | Treatment Plan list after initial check | Presenter transitions to master treatment plan. |
| 00:45 | `captures/phrase-06-045s.png` | Master plan row/version | Master created on 03/03, within 30 days of admission. |
| 01:02 | `captures/phrase-08-062s.png` | Master Treatment Plan modal, signature area | Client and therapist/staff signatures both present; reviewer signature also appears. |
| 01:11 | `captures/phrase-09-071s.png` | Treatment Plan version/history | Presenter says this version history is not the preferred source for tracking updates. |
| 01:33 | `captures/phrase-12-093s.png` | Current Overview, Treatment Plan Reviews row | Treatment Plan Reviews appears in a left list inside Current Overview with a table to the right. |
| 01:48 | `captures/phrase-14-108s.png` | Level of Care panel | IOP-5 row has no discharge date, so it is current. Previous PHP row has a discharge/stepdown date. |
| 02:04 | `captures/phrase-15-124s.png` | LOC cadence discussion | PHP requires 30-day reviews during PHP range. |
| 02:12 | `captures/phrase-16-132s.png` | IOP-5 cadence discussion | IOP-5 requires 60-day reviews; current LOC established by blank discharge date. |
| 02:31 | `captures/phrase-18-151s.png` | Treatment Plan Review modal | Document-style modal with demographics and clinical sections. |
| 02:45 | `captures/phrase-19-165s.png` | Review document scroll | Presenter scrolls toward date and signature evidence. |
| 02:59 | `captures/phrase-21-179s.png` | Review staff signature | Staff signature dated 04/02; client signature area can be blank for reviews. |
| 03:25 | `captures/phrase-24-205s.png` | Signature section while discussing current process | Presenter describes checking due date when reviews come for signature. |
| 03:36 | `captures/phrase-25-216s.png` | Next Review Due field | Visible next due date is 05/29. This is an important logic cross-check. |
| 03:45 | `captures/phrase-26-225s.png` | Asana discussed, not shown | Presenter says she currently goes to Asana and uses its date section to track due dates. |
| 04:03 | `captures/phrase-28-243s.png` | Closing value statement | Goal is a trustworthy tracker for nearly 60 active clients. |

## Visual Flow Summary

1. Start from client overview.
2. Verify initial and master plans in Treatment Plan tab.
3. Use signatures in printable document modals as decisive evidence.
4. Switch to Current Overview for Treatment Plan Reviews.
5. Cross-check LOC history to explain review cadence.
6. Open review document, find `Next Review Due`, and verify staff signature date.
7. Replace manual Asana tracking with a trustworthy in-app queue.
