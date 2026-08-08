

I traced the active template, JavaScript, server validation, and persistence logic. The screen does support AI-only review, human-only revision, or both—but several important inconsistencies exist.

## Actual submission behaviour

| Screen activity | Accepted? | What is persisted | Current `has_review` |
|---|---:|---|---:|
| AI status only | Yes | AI status, reviewer and timestamp | No |
| AI comment only | Yes | AI comment, reviewer and timestamp | No |
| Human grade | Yes | `review`-role grade; final consensus overwritten if task is final | Yes |
| Human comment without grade | No | Nothing | No |
| Both panels | Yes | Both sets of data | Yes |
| Neither panel | No | Validation error | No |
| Cancel & Next | Yes | Nothing | Unchanged |

The server-side validation allowing either a human grade or AI feedback is in [task_review.py](/fundus_img_xtract/review/task_review.py:332).

## Frontend JavaScript

The screen actively uses [review-task-detail.js](/fundus_img_xtract/static/js/review-task-detail.js:150).

It:

- shows the human comment, features and AI-influence question only after selecting a human grade;
- restores an existing human review selection;
- makes the AI-influence question mandatory for a human revision when AI is visible;
- shows a confirmation modal before a human review overwrites a final consensus;
- allows AI-only feedback to submit without the consensus-warning modal;
- lets Cancel & Next proceed without saving.

The JavaScript does not check whether the AI fields changed or determine consolidated review status. The backend performs the substantive validation.

## Server-side validation

The backend correctly verifies:

- discrepancy-reviewer role and hospital scope;
- eligible consensus method;
- valid AI status: `ok`, `minor_miss`, or `major_miss`;
- at least one human-grade or AI-feedback action;
- valid active human grade for the disease;
- valid features belonging to the selected grade;
- mandatory AI-influence response when revising the human grade with AI visible.

Human revision and AI feedback are committed atomically. Exceptions trigger rollback.

## Important problems found

### 1. `Has Review` excludes AI-only reviews

AI-only submission updates:

```text
ai_review_status
ai_review_comment
ai_reviewed_by_user_id
ai_reviewed_at
```

But it does not create a `review`-role grade.

The materialized view defines `has_review` only as the existence of `role_slot='review'` in [mvw_image_listing_v2.py](/fundus_img_xtract/utils/mvw_image_listing_v2.py:269). Therefore, AI-only reviews remain `has_review=false`.

### 2. AI-influence labels and stored values are reversed

The template currently contains:

```text
value="yes" → “Updated NOT based on AI result”
value="no"  → “Updated based on AI result”
```

See [task_detail_review.html](/fundus_img_xtract/templates/review/task_detail_review.html:349).

The backend stores those values literally as:

```text
AI influence: yes
AI influence: no
```

Consequently, the stored AI-influence interpretation is opposite to the label selected by the reviewer. This should be treated as a substantive data-quality bug.

### 3. Existing AI feedback can have its audit information overwritten

Existing AI status/comment values are pre-populated in the form. On any subsequent submission, the backend treats those unchanged values as newly submitted feedback and rewrites:

```text
ai_reviewed_by_user_id
ai_reviewed_at
```

Thus, a later human-grade revision can incorrectly replace the identity and date of the person who originally assessed the AI.

### 4. Existing AI feedback cannot be cleared

If the reviewer changes the status to “No assessment” and empties the comment, the backend skips that AI record rather than setting its fields to null. The old AI feedback remains in the database.

### 5. “Clear Selections” clears only the human panel

The JavaScript clears:

- human grade;
- human comment;
- features;
- AI-influence choice.

It does not clear the AI status or AI comment, despite the general button label.

### 6. Existing human review is automatically resubmitted

When a human review already exists, JavaScript automatically reselects it. A later AI-feedback update can therefore also update the existing human review and overwrite the final consensus again unless the reviewer explicitly clears the human selection.

### 7. Review lists can remain temporarily stale

After submission, the code clears the page cache but does not refresh the materialized view used by the Discrepancy Review query. The page and Save & Next queue may therefore retain stale review status until the scheduled materialized-view refresh.

### 8. Focused tests are missing

I found tests for discrepancy filter construction, but no focused tests covering:

- AI-only review submission;
- human-only review;
- combined submission;
- clearing AI feedback;
- reviewer/timestamp preservation;
- final-consensus overwrite;
- consolidated `has_review`;
- frontend AI-influence value mapping.

## Overall conclusion

The post-April workflow is implemented as two independent review actions on one screen. That part is intentional and functional. However, the app does not persist a task-level “review event,” so `Has Review` currently means only “human grade revised,” not “this screen was reviewed.”

The most urgent corrections are:

1. fix the reversed AI-influence values;
2. define consolidated review from either panel;
3. preserve the original AI reviewer and timestamp unless AI feedback actually changes;
4. support intentional clearing of AI feedback;
5. refresh or directly query current review state after submission.
