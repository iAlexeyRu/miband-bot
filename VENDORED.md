# Vendored Dependencies

This repository currently vendors the Xiaomi Fitness SDK source under `mi-fitness-python/`.

## `mi-fitness-python`

- Upstream repository: `https://github.com/MistEO/MiSDK`
- Package/import name: `mi-fitness` / `mi_fitness`
- Vendored path: `mi-fitness-python/`
- License: GNU GPL v3.0, see `mi-fitness-python/LICENSE`
- Upstream author metadata: `Misty02600 <xiao02600@gmail.com>` in `mi-fitness-python/pyproject.toml`

## Why It Is Vendored

The bot depends on Xiaomi Fitness behavior that can change without notice. Keeping the SDK source in-tree makes the Docker image and local development workflow self-contained:

- users can clone one repository and run Docker Compose;
- CI does not depend on a separate unpublished fork;
- local fixes for Xiaomi API changes can be tested together with the bot.

## Update Policy

When updating `mi-fitness-python`:

1. Record the upstream repository URL and commit/tag used.
2. Preserve upstream license and attribution files.
3. Keep local changes small and documented in the pull request.
4. Run both root tests and `mi-fitness-python/tests/unit`.
5. Avoid unrelated formatting churn in vendored files.

If the SDK stabilizes as a public package that contains all required fixes, the project can later move from vendoring to a PyPI dependency. Until then, vendoring is the preferred release path for user-friendly Docker setup.
