import unittest

from app.schemas import LiveAudienceProfileResponse


class ProfileRow:
    dimension_type = "age"
    dimension_name = "31-40"
    ratio = 44
    count = 0


class LiveSessionDetailsTest(unittest.TestCase):
    def test_profile_response_accepts_orm_rows(self):
        profile = LiveAudienceProfileResponse.model_validate(ProfileRow())
        self.assertEqual(profile.dimension_type, "age")
        self.assertEqual(profile.ratio, 44)


if __name__ == "__main__":
    unittest.main()
