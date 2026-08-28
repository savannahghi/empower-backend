Feature: Organisation and Branch Settings

  Scenario: Get all organisation settings
    Given I am an authenticated user
    When I send a GET request to "org_settings"
    Then I receive a 200 OK response
    And I receive 26 organisation settings

  Scenario: Get all branch settings
    Given I am an authenticated user
    And the branch ID is "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"
    When I send a GET request to "branch_settings"
    Then I receive a 200 OK response
    And I receive 13 branch settings

  Scenario: Update a branch setting
    Given I am an authenticated user
    And the branch ID is "f249c5e2-d4b9-4a24-8ce2-83451aeb837e"
    When I send a PATCH request to "branch_settings" with branch ID and the JSON
      """
      [
        {
          "name": "scheduling:appointment_reminder_timings",
          "value": [
            12
          ]
        }
      ]
      """
    Then I receive a 200 OK response
    And the branch setting "scheduling:appointment_reminder_timings" is updated to "12"
    And the description is "Promotional Sender ID"
    And the setting type is "str"

  Scenario: Update an organisation setting
    Given I am an authenticated user
    When I send a PATCH request to "/org_settings/" with the following JSON
      """
      [
        {
          "name": "patients:patient_id_format",
          "value": "OREGON/{file_number:04d}"
        }
      ]
      """
    Then I receive a 200 OK response
    And the organisation setting "patients:patient_id_format" is updated to "OREGON/{file_number:04d}"
    And the description is "Patient ID Format"
    And the setting type is "str"
