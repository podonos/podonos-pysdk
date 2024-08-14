import unittest
from podonos.core.query import Query, Question


class TestQuery(unittest.TestCase):
    def test_query_with_not_null(self):
        TITLE = "This is custom question"
        DESCRIPTION = "This is custom description"
        QUESTION_DICT = {"title": TITLE, "description": DESCRIPTION}
        QUERY_DICT = {"question": QUESTION_DICT}

        question = Question(TITLE, DESCRIPTION)
        query = Query(question=question)
        self.assertTrue(query.title == TITLE)
        self.assertTrue(query.description == DESCRIPTION)
        self.assertTrue(question.title == TITLE)
        self.assertTrue(question.description == DESCRIPTION)
        self.assertTrue(query.question == question)
        self.assertTrue(query.question.to_dict() == QUESTION_DICT)
        self.assertTrue(query.to_dict() == QUERY_DICT)

    def test_query_with_null(self):
        TITLE = "This is custom question"
        DESCRIPTION = None
        QUESTION_DICT = {"title": TITLE, "description": DESCRIPTION}
        QUERY_DICT = {"question": QUESTION_DICT}

        question = Question(TITLE, DESCRIPTION)
        query = Query(question=question)
        self.assertTrue(query.title == TITLE)
        self.assertTrue(query.description == DESCRIPTION)
        self.assertTrue(question.title == TITLE)
        self.assertTrue(question.description == DESCRIPTION)
        self.assertTrue(query.question == question)
        self.assertTrue(query.question.to_dict() == QUESTION_DICT)
        self.assertTrue(query.to_dict() == QUERY_DICT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
