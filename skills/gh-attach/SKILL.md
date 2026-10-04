---
name: "gh-attach"
description: "将本地文件（截图、图片、PDF、ZIP、视频等）上传至 GitHub user-attachments、下载 GitHub 附件，并直接嵌入到 PR、Issue 或评论中。适用于“向 PR 附上截图”、“在 Issue 中添加图片”、“嵌入前后对比截图”、“附加此文件”或“下载该 GitHub 附件”等需求。基于 `gh-attach` 构建。"
version: "1.0.0"
license: "MIT"
---
# gh-attach

`gh attach` uploads a file to GitHub's internal user-attachments endpoint (no public API exists) and prints the URL, which GitHub auto-renders (image/video/file) wherever it's pasted. The URL inherits the repo's visibility, so private-repo uploads stay private.

## Prerequisites

```sh
gh extension list | grep -q 'gh attach' || gh extension install sudosubin/gh-attach
```

Uploads use a GitHub browser session cookie, not the `gh` token. By default, `gh` must be authenticated so `gh-attach` can select the matching browser account. If the wrong account is selected, add `--browser <name> --profile <name>`. For headless use, set `GH_ATTACH_SESSION_TOKEN` to the bare `user_session` cookie value. Treat it as a full account credential.

## Steps

**1. Upload**: Use an absolute quoted path. `-R` is optional inside a repository. For GHES, use `-R host/owner/repo`. The command prints the URL on one line. GitHub auto-renders it (image/video/file), so use it as-is:

```sh
URL=$(gh attach "$FILE" -R <owner>/<repo>)
```

**2. Embed** (always `--body-file -`, e.g. `gh pr comment/edit`, `gh issue comment/edit`):

```sh
printf '## Screenshots\n\n%s\n' "$URL" | gh pr comment <pr> -R <owner>/<repo> --body-file -
```

**3. Download**: Specify the destination explicitly. Private attachments use the active `gh` token, with browser cookies as an authorization fallback:

```sh
gh attach download "$URL" -O "$FILE"
```

## Notes

- Private repo: URL renders only for authorized viewers. An anonymous fetch is expected to return 404 or 403.
- Sizing: embed `<img width="800" src="$URL">` instead of the bare URL.
- GitHub Cloud and GHES decide which file extensions and content types they accept.

