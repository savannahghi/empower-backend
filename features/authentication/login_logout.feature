Feature: User logs in and out using the API

    Scenario: A user logs in
        Given An active user sends login request with correct credentials
        Then The user should get a key in the response

