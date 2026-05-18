import unittest

from rag_chain import answer_question


class PortfolioAssistantTests(unittest.TestCase):
    def answer(self, question):
        return answer_question(question)["answer"]

    def test_data_engineer_profile_answer(self):
        answer = self.answer("Who is Abhishek?")
        self.assertIn("Data Engineer", answer)
        self.assertIn("2+ years", answer)

    def test_data_warehousing_answer(self):
        answer = self.answer("What data warehousing experience does Abhishek have?")
        self.assertIn("Medallion Architecture", answer)
        self.assertIn("SCD Type 2", answer)
        self.assertIn("Delta Lake", answer)

    def test_python_skills_answer(self):
        answer = self.answer("What are Abhishek's Python skills and tools?")
        self.assertIn("Python", answer)
        self.assertIn("PySpark", answer)
        self.assertIn("Azure Data Factory", answer)

    def test_project_claim_consistency(self):
        answer = self.answer("Tell me about the Zomato NLP project")
        self.assertIn("20K+ reviews", answer)
        self.assertIn("85% accuracy", answer)
        self.assertNotIn("1M+ reviews", answer)
        self.assertNotIn("90% accuracy", answer)

    def test_out_of_scope_pricing_refuses(self):
        answer = self.answer("Tell me about pricing for custom dashboards")
        self.assertIn("do not have verified pricing", answer)

    def test_booking_intent_flow(self):
        answer = self.answer("Can I book a call with Abhishek?")
        self.assertIn("Please share these details", answer)
        self.assertIn("Name", answer)

    def test_book_chapter_specific_answer(self):
        answer = self.answer("What is chapter 4 of this book about?")
        self.assertIn("Chapter 4", answer)
        self.assertIn("The Bruises Before I Understood Hurt", answer)
        self.assertIn("childhood pain", answer)
        self.assertNotIn("opening sections include a dedication", answer)

    def test_book_chapter_20_answer(self):
        answer = self.answer("What is in chapter 20?")
        self.assertIn("Chapter 20", answer)
        self.assertIn("The Quiet Grind", answer)
        self.assertIn("self-discipline", answer)
        self.assertNotIn("opening sections include a dedication", answer)

    def test_book_letter_to_baba_answer(self):
        answer = self.answer("What is the letter to Baba about?")
        self.assertIn("Letter 1", answer)
        self.assertIn("To Baba", answer)
        self.assertIn("grief-and-gratitude", answer)
        self.assertNotIn("opening sections include a dedication", answer)

    def test_book_missing_chapter_answer(self):
        answer = self.answer("What is in chapter 50?")
        self.assertIn("could not find Chapter 50", answer)


if __name__ == "__main__":
    unittest.main()
