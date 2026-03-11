# Contributing to ContextuAI Solo

Thank you for your interest in contributing to ContextuAI Solo! This document provides guidelines and instructions for contributing.

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/solo.git
   cd solo
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** and test them thoroughly
5. **Commit** with a clear, descriptive message:
   ```bash
   git commit -m "feat: add new agent for supply chain analysis"
   ```
6. **Push** to your fork and **open a Pull Request**

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `style:` — Formatting, no code change
- `refactor:` — Code restructuring without feature change
- `test:` — Adding or updating tests
- `chore:` — Build, tooling, or dependency updates

## Code Style

### TypeScript (Frontend)

- **Strict mode** is enabled — no `any` types without justification
- Use functional components with hooks
- Use the `cn()` utility for conditional Tailwind classes
- Import paths use the `@/*` alias (maps to `src/*`)
- Format with Prettier defaults

### Python (Backend)

- **Type hints** on all function signatures and return types
- Use **Pydantic v2** for request/response models
- All I/O must be **async** (use `await`, async generators for streaming)
- Follow PEP 8 naming conventions
- Docstrings on public functions and classes

## Testing

### Frontend

```bash
cd desktop
npm run test        # Unit tests
npx playwright test # E2E tests
```

### Backend

```bash
cd backend
pytest tests/ -v
```

All pull requests must:

- Pass existing tests (no regressions)
- Include tests for new features when applicable
- Pass linting (`npm run lint` for frontend)

## What to Contribute

Here are some ideas for contributions:

- **New agents** — Add specialized business agents to the library
- **Bug fixes** — Check the Issues tab for reported bugs
- **UI/UX improvements** — Better layouts, animations, accessibility
- **Documentation** — Improve docs, add examples, fix typos
- **New AI provider integrations** — Add support for additional model providers
- **Localization** — Help translate the UI to other languages
- **Performance** — Optimize rendering, reduce bundle size, improve startup time

## Reporting Issues

When reporting a bug, please include:

- Your OS and version
- Steps to reproduce the issue
- Expected behavior vs actual behavior
- Screenshots or error logs if applicable

## Code of Conduct

Be respectful, constructive, and inclusive. We are building something together — treat every contributor the way you would want to be treated.

## Questions?

Open a GitHub Discussion or reach out to the maintainers. We're happy to help you get started.

---

Thank you for helping make ContextuAI Solo better for everyone!
