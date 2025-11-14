from typing import List

from requests import HTTPError

from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.script import ScriptCreateRequestDto
from podonos.entity.script import ScriptEntity
from podonos.common.validator import Rules, validate_args


class ScriptService:
    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    @validate_args(collection_id=Rules.uuid_not_none, texts=Rules.list_not_none)
    def create_all(self, collection_id: str, texts: List[str]) -> List[ScriptEntity]:
        """
        Create new scripts for a collection

        Args:
            collection_id: The ID of the collection
            texts: List of texts to create scripts for
                - The length of text must be over 1 character

        Returns:
            List of created scripts

        Raises:
            HTTPError: If the request fails
        """
        log.info(f"Create scripts for collection: {collection_id}")

        try:
            request = ScriptCreateRequestDto.from_dict(collection_id, texts)
            response = self.api_client.post("scripts", data=request.to_create_request_dto())
            response.raise_for_status()
            return [ScriptEntity.from_dict(item) for item in response.json()]
        except Exception as e:
            raise HTTPError(f"Failed to create scripts: {e}")

    @validate_args(collection_id=Rules.uuid_not_none)
    def list(self, collection_id: str) -> List[ScriptEntity]:
        """
        Get the list of all scripts

        Returns:
            List of all scripts

        Raises:
            HTTPError: If the request fails
        """
        log.debug(f"Get the list of scripts for collection: {collection_id}")
        try:
            response = self.api_client.get(f"scripts?collection-id={collection_id}")
            response.raise_for_status()
            return [ScriptEntity.from_dict(item) for item in response.json()]
        except Exception as e:
            raise HTTPError(f"Failed to get the list of scripts: {e}")
