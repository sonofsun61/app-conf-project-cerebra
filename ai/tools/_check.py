from ai.tools.check_commit_safety import check_commit_safety


print("name:", check_commit_safety.name)

print(
    "ok:",
    check_commit_safety.run(
        scope="staged",
        max_file_size_kb=1024,
    ),
)

print(
    "err:",
    check_commit_safety.run(
        scope="wrong_scope",
        max_file_size_kb=1024,
    ),
)