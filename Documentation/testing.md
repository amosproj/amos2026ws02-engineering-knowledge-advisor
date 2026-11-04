# Testing Guidelines

## Automated Testing

- **Pipeline & Hooks**: Unit and integration tests are run in the CI pipeline and locally in pre-commit hooks
- **Test Coverage**: There is no specific required test coverage, but tests are required for all features
- **End-to-End (E2E)**: There are no automated end-to-end tests, as they are maintenance heavy and therefore very time-consuming

## Manual Testing

- **Manual Verification**: Every new feature has to be tested manually before merging
- **AI Features**: APIs with free tiers available that can be used for testing
- **API endpoints**: A REST client (Postman, Insomnia, ...) and the OpenAPI contract should be used for testing
- **Demo Environment**: A demo is hosted at [https://ek-advisor.com](https://ek-advisor.com)
