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
        self.assertEqual(query.title, TITLE)
        self.assertEqual(query.description, DESCRIPTION)
        self.assertEqual(question.title, TITLE)
        self.assertEqual(question.description, DESCRIPTION)
        self.assertEqual(query.question, question)
        self.assertEqual(query.question.to_dict(), QUESTION_DICT)
        self.assertEqual(query.to_dict(), QUERY_DICT)

    def test_query_with_null(self):
        TITLE = "This is custom question"
        DESCRIPTION = None
        QUESTION_DICT = {"title": TITLE, "description": DESCRIPTION}
        QUERY_DICT = {"question": QUESTION_DICT}

        question = Question(TITLE, DESCRIPTION)
        query = Query(question=question)
        self.assertEqual(query.title, TITLE)
        self.assertEqual(query.description, DESCRIPTION)
        self.assertEqual(question.title, TITLE)
        self.assertEqual(question.description, DESCRIPTION)
        self.assertEqual(query.question, question)
        self.assertEqual(query.question.to_dict(), QUESTION_DICT)
        self.assertEqual(query.to_dict(), QUERY_DICT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
