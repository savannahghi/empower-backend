Deployment
----------

Making Releases
~~~~~~~~~~~~~~~

1. Pull all tags from remote: `git pull --tags`
2. Update the changelog by running `make changelog`
3. Find the new version in `CHANGELOG.md` and update `VERSION` in `setup.py`
4. Create a release commit (it must start with `chore`, e.g. "chore: Release 0.4.0")
5. Create a tag: `git tag <version>` e.g. `git tag 0.4.0`
6. Push commit to remote: `git push`
7. Push tags to remote: `git push --tags`
