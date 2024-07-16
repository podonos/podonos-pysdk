## 0.1.16

- Add `soundfile` library
- Support only `wav` format

## 0.1.13

- Fix bug when initializing `Evaluator`

## 0.1.12

- Create `File` object for containing `path`, `tags`
- Make `tags` field as a list of string
- Replace arguments(`path`, `tags`) of `add_file` into `file` (`File` Object)
- Fix bugs in Similarity MOS by `add_file_set`
- Change the return key of `get_stats_by_id` into [`files`, `mean`, `median`, `std`, `ci_90`, `ci_95`, `ci_99`]
- Change the column of `download_stats_csv_by_id` into [`name`, `tags`, `median`, `std`, `ci_90`, `ci_95`, `ci_99`]

## 0.1.11

- Store the duration of file
- Add more languages like mandarin, italian, japan, french, german

## 0.1.10

- Allow accessing the evaluation results.
- Ensure more stability.
- Add more unit tests. Reached 70% of test coverage.
- Fix bugs.

## 0.1.6

- Fix duplicate upload bug.

## 0.1.5

- Access all the evaluations and their details.
- Support multiple English languages.

## 0.1.1

- Add evaluation notifications.

## 0.1.0

- Support Similarity MOS
- Fix timestamp format issue.
