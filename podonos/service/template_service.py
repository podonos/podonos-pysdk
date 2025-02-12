from typing import List
from requests import HTTPError
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.template import Template
from podonos.core.types import TemplateOption, TemplateQuestion


class TemplateService:
    """Service class for handling template-related API communications"""

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

    def create_template_questions_by_evaluation_id_and_questions(self, evaluation_id: str, template_questions: List[TemplateQuestion]) -> dict:
        """
        Create template questions by evaluation id and question list
        """
        try:
            log.debug(f"Creating {len(template_questions)} template questions for evaluation {evaluation_id}")
            response = self.api_client.put(
                f"template-questions/bulk", data={"evaluation_id": evaluation_id, "questions": [q.to_create_dict() for q in template_questions]}
            )
            response.raise_for_status()
            log.debug(f"Create template questions by evaluation id {evaluation_id}")
            return response.json()
        except Exception as e:
            raise HTTPError(f"Failed to create template questions by evaluation id: {evaluation_id} / {e}")

    def create_template_options_by_question_id_and_options(self, template_question_id: str, template_options: List[TemplateOption]) -> dict:
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
            return response.json()
        except Exception as e:
            raise HTTPError(f"Failed to create template options by question id: {template_question_id} / {e}")
