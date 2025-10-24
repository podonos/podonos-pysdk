## 0.27.0

- Support multiple reference files for instruction questions (max 3 files)
- Deprecate `reference_file` field in favor of `reference_files` for instruction questions
- Add `EXAMPLE` instruction category for providing examples to evaluators
- Update file type validation to use `audio`, `reference`, `target` (consistent with server)
- Add `upload_reference_files_by_url_and_file_paths` method to TemplateService for uploading multiple reference files

## 0.26.0

- Add support for pt-br (Portuguese Brazil) language and fr-ca (French Canada) in evaluations
- Add log when Audio length is under 500ms
- Add file type validation (via content detection) to block mismatched extensions (e.g., .wav file containing MP4); supported formats: wav, mp3, flac.

## 0.25.0

- Add support for pt-pt (Portuguese Portugal) language in evaluations

## 0.24.0

- Add support for en-in (Indian English) language in evaluations
- Add comprehensive test coverage for en-in language support
- Improve Python 3.8+ compatibility with proper type hints

## 0.23.0

- Add `Retry` logic into every API calls
- The number of files: 460
- 100 ms latency / 10% packet loss: 4m 41s
- 100 ms latency / 20% packet loss: 10m 42s
- 100 ms latency / 30% packet loss: 21m 22s

## 0.21.0

- Add `Retry` logic when calling API

## 0.20.0
- Add `auto_start` to create_from_template
- Add `get_eval_template_info()`

## 0.19.0

- Support `CMOS` evaluation type

## 0.18.0

- Support `use_auto_analysis` option in evaluator

## 0.17.0

- Implement data collection feature
- Support Create evalautor from CSMOS template

## 0.16.0

- Get evaluation files by `download_evaluation_files_by_evaluation_id`

## 0.15.0

- Select the `related_model` when creating `Evaluation` in `template`

## 0.14.0

- Remove `download_stats_csv_by_id`
- Rename `get_stats_dict_by_id` into `get_stats_json_by_id`

## 0.13.0

- Add `group_by` option in `get_stats_dict_by_id`

## 0.12.0

- Support `CSMOS` for evaluation
- Add `num_eval`'s default value in `create_evaluator_from_template`


## 0.11.0

- Fix the bug of `get_stats_by_evaluator` (`OTHER` is not included in the stats)
- Add `anchor_label` in `create_evaluator_from_template_json`

## 0.10.0

- Remove `use_annotation` option in `create_evaluator_from_template`

## 0.9.0

- Create `TemplateService` for interacting template
- Change interface of JSON used in `create_evaluator_from_template_json`

## 0.8.1

- Handle the error of `get_audio_info` when using `soundfile` library

## 0.8.0

- Change the API key verification method
- Remove `SingleStimlusEvaluator` and `DoubleStimlusEvaluator`
- Create `EvaluationService` class for managing evaluations

## 0.7.0

- Fix the bug of `get_stats_dict_by_id` and `download_stats_csv_by_id`
- Add `use_loudness_normalization` option in `create_evaluator` and `create_evaluator_from_template`
- Create evaluator from template JSON `create_evaluator_from_template_json`

## 0.6.0

- `create_evaluator_from_template`: Creating evaluation from template's unique code
- `create_evaluator`: The CUSTOM_SINGLE and CUSTOM_DOUBLE are supported

## 0.5.0

- Remove the duplicate tags

## 0.4.0

- Split the audio's list into several chunk per 500

## 0.3.0

- Remove `set_question` because the custom query is done in web
- Fix the auto_start option in evaluation

## 0.2.2

- Removed `add_file_pair` and `add_file_set`. Added `add_files` instead.
- Made the file upload 6x faster by putting an API call into threads.

## 0.2.0

- Add `set_question` for custom question and description
- Increase the speed of uploading files
- Add `type` (A, B) field into `get_stats_dict_by_id` 

## 0.1.19

- Add `script` into `File`
- Remove coloring text
- Add `META` type for non audio file
- Add `order_in_group` for finding the order of files in a query

## 0.1.18

- Create `random_uuid_path` of `file` before uploading `file`

## 0.1.17

- Create `Preference` type for evaluation
- Support `mp3` format

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
