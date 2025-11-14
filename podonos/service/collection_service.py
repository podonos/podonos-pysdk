from typing import List, Optional

from requests import HTTPError

from podonos.common.enum import CollectionTarget, Language
from podonos.core.api import APIClient
from podonos.core.base import log
from podonos.core.collection import CollectionCreateRequestDto
from podonos.entity.collection import CollectionEntity
from podonos.common.validator import Rules, validate_args


class CollectionService:
    def __init__(self, api_client: APIClient) -> None:
        self.api_client = api_client

    @validate_args(
        name=Rules.str_non_empty,
        desc=Rules.str_not_none_or_none,
        lan=Rules.str_not_none,
        num_required_people=Rules.int_not_none,
        target=Rules.str_not_none,
    )
    def create(
        self,
        name: str,
        desc: Optional[str] = None,
        lan: str = Language.ENGLISH_AMERICAN.value,
        num_required_people: int = 10,
        target: str = CollectionTarget.AUDIO.value,
    ) -> CollectionEntity:
        """
        Create a new collection

        Args:
            name: The name of the collection
            desc: The description of the collection
            lan: The language of the collection. Default: en-us
            num_required_people: The number of required people for the collection. Default: 10
            target: The target of the collection. Default: AUDIO

        Returns:
            The created collection

        Raises:
            HTTPError: If the request fails
        """
        log.info(f"Create collection: {name}")

        try:
            request = CollectionCreateRequestDto.from_dict(name, desc, lan, num_required_people, target)
            response = self.api_client.post("collections", data=request.to_create_request_dto())
            response.raise_for_status()
            collection = CollectionEntity.from_dict(response.json())
            log.info(f"Collection is generated: {collection.id}")
            return collection
        except Exception as e:
            raise HTTPError(f"Failed to create the collection: {e}")

    def list(self) -> List[CollectionEntity]:
        """
        Get the list of collections

        Returns:
            The list of collections ordered by created_time

        Raises:
            HTTPError: If the request fails
        """
        log.debug("Get the list of collections")
        try:
            response = self.api_client.get("collections")
            response.raise_for_status()
            return [CollectionEntity.from_dict(item) for item in response.json()]
        except Exception as e:
            raise HTTPError(f"Failed to get the list of collections: {e}")
