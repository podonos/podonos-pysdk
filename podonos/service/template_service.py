from typing import List, Optional
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.template import Template
from podonos.core.types import TemplateOption, TemplateQuestion
from podonos.common.exception import HTTPError


class TemplateService:
    """Service class for handling template"""

    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    def get_template_by_code(self, template_id: str) -> Template:
        """
        Get template information by Id

        Returns: Template
        """
        try:
            response = self.api_client.get(f"templates/one?code={template_id}")
            response.raise_for_status()
            template = Template.from_api_response(response.json())
            log.info(f"Get template by id {template_id}")
            return template
        except Exception as e:
            raise HTTPError(f"Failed to get template by id: {template_id} / {e}")

    def create_template_questions_by_evaluation_id_and_questions(
        self, evaluation_id: str, template_questions: List[TemplateQuestion]
    ) -> List[TemplateQuestion]:
        """
        Create template questions by evaluation id and question list

        Returns: List of TemplateQuestion
        """
        try:
            log.debug(f"Creating {len(template_questions)} template questions for evaluation {evaluation_id}")
            response = self.api_client.put(
                f"template-questions/bulk", data={"evaluation_id": evaluation_id, "questions": [q.to_create_dict() for q in template_questions]}
            )
            response.raise_for_status()

            log.debug(f"Create template questions by evaluation id {evaluation_id}")
            for q_response, question in zip(response.json(), template_questions):
                question.id = q_response["id"]
            return template_questions
        except Exception as e:
            raise HTTPError(f"Failed to create template questions by evaluation id: {evaluation_id} / {e}")

    def create_template_options_by_question_id_and_options(
        self, template_question_id: str, template_options: List[TemplateOption]
    ) -> List[TemplateOption]:
        """
        Create template options by question id and option list
        """
        try:
            log.debug(f"Creating {len(template_options)} template options for question {template_question_id}")
            response = self.api_client.put(
                f"template-options/bulk", data={"template_question_id": template_question_id, "options": [opt.to_dict() for opt in template_options]}
            )
            response.raise_for_status()
            log.debug(f"Create template options by question id {template_question_id}")
            for opt_response, option in zip(response.json(), template_options):
                option.id = opt_response["id"]
            return template_options
        except Exception as e:
            raise HTTPError(f"Failed to create template options by question id: {template_question_id} / {e}")

    def get_presigned_url_by_template_question_id(self, template_question_id: str) -> str:
        """
        Get presigned url by template question id
        """
        try:
            # Step 1: Get presigned URL
            response = self.api_client.post(f"template-questions/{template_question_id}/reference-uri", data={})
            response.raise_for_status()
            return response.text.replace('"', "")
        except Exception as e:
            log.error(f"Failed to get presigned URL for template question id: {template_question_id} / {e}")
            raise HTTPError(f"Failed to get presigned URL for template question id: {template_question_id} / {e}")

    def get_presigned_url_by_template_option_id(self, template_option_id: str) -> str:
        """
        Get presigned url by template option id
        """
        try:
            response = self.api_client.post(f"template-options/{template_option_id}/reference-uri", data={})
            response.raise_for_status()
            return response.text.replace('"', "")
        except Exception as e:
            log.error(f"Failed to get presigned URL for template option id: {template_option_id} / {e}")
            raise HTTPError(f"Failed to get presigned URL for template option id: {template_option_id} / {e}")

    def upload_reference_file_by_url_and_file_path(
        self, url: str, file_path: str, question_id: Optional[str] = None, option_id: Optional[str] = None
    ) -> None:
        """
        Upload reference file by url and file path
        """
        try:
            with open(file_path, "rb") as file:
                upload_response = self.api_client.external_put(url, data=file)
                upload_response.raise_for_status()

            log.debug(f"Successfully uploaded reference file {file_path} of Template by url")
        except Exception as e:
            if question_id:
                self.api_client.delete(f"template-questions/{question_id}/reference-uri")
                raise HTTPError(f"Failed to upload reference file by question id: {question_id} / {e}")
            elif option_id:
                self.api_client.delete(f"template-options/{option_id}/reference-uri")
                raise HTTPError(f"Failed to upload reference file by option id: {option_id} / {e}")
            else:
                raise HTTPError(f"Failed to upload reference file by url: {url} / {e}")
