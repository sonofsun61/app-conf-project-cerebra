# Контракт Tool (воркшоп 1)
#
# Имя:
# check_commit_safety
#
# Назначение:
# Проверяет файлы проекта перед Git-коммитом и сообщает о потенциально
# небезопасных или нежелательных для публикации данных.
# Используй этот Tool, когда пользователь просит проверить проект перед
# коммитом, убедиться, что в Git не попадут секреты, временные файлы,
# служебные каталоги, слишком большие файлы или незакрытые merge-конфликты.
#
# Tool только анализирует проект и НЕ удаляет, НЕ изменяет и НЕ добавляет
# файлы в Git.
#
# Вход:
#
# scope: str — необязательный параметр, по умолчанию "staged".
# Допустимые значения:
#   "staged"      — проверять только файлы, подготовленные к коммиту
#                   через git add;
#   "all_tracked" — проверять все файлы, которые отслеживаются Git.
#
# max_file_size_kb: int — необязательный параметр, по умолчанию 1024.
# Максимальный допустимый размер одного файла в килобайтах.
# Допустимый диапазон: от 1 до 10240 включительно.
#
# Выход:
# Всегда JSON-строка.
#
# При успешном выполнении проверки:
# {
#     "status": "ok",
#     "scope": "staged",
#     "safe_to_commit": true,
#     "checked_files": 12,
#     "issues_count": 0,
#     "issues": []
# }
#
# Если обнаружены проблемы:
# {
#     "status": "ok",
#     "scope": "staged",
#     "safe_to_commit": false,
#     "checked_files": 12,
#     "issues_count": 3,
#     "issues": [
#         {
#             "type": "secret",
#             "severity": "critical",
#             "path": "config.py",
#             "line": 15,
#             "message": "Обнаружен возможный API-ключ"
#         },
#         {
#             "type": "unwanted_file",
#             "severity": "warning",
#             "path": "debug.log",
#             "line": null,
#             "message": "Лог-файл обычно не следует добавлять в репозиторий"
#         },
#         {
#             "type": "large_file",
#             "severity": "warning",
#             "path": "data/dump.json",
#             "line": null,
#             "message": "Размер файла превышает установленный лимит"
#         }
#     ]
# }
#
# При ошибке самого Tool:
# {
#     "status": "error",
#     "message": "<что произошло и как это исправить>"
# }
#
# Проверки:
#
# 1. Потенциальные секреты:
#    - API keys;
#    - access tokens;
#    - passwords;
#    - private keys;
#    - файлы .env;
#    - credentials.json;
#    - *.pem;
#    - *.key;
#    - id_rsa.
#
#    ВАЖНО:
#    Tool никогда не возвращает найденное значение секрета.
#    В ответе указываются только тип проблемы, путь к файлу и номер строки.
#
# 2. Нежелательные файлы и каталоги:
#    - __pycache__/;
#    - .pytest_cache/;
#    - .mypy_cache/;
#    - .ruff_cache/;
#    - .venv/;
#    - venv/;
#    - node_modules/;
#    - *.pyc;
#    - *.log;
#    - .DS_Store;
#    - Thumbs.db;
#    - временные файлы.
#
# 3. Слишком большие файлы:
#    - файл считается проблемным, если его размер превышает
#      max_file_size_kb.
#
# 4. Незавершённые merge-конфликты:
#    - <<<<<<<
#    - =======
#    - >>>>>>>
#
# Краевые случаи:
#
# - scope имеет значение, отличное от "staged" или "all_tracked":
#   вернуть status="error" и перечислить допустимые значения.
#
# - max_file_size_kb меньше 1 или больше 10240:
#   вернуть status="error" с допустимым диапазоном.
#
# - текущая директория не является Git-репозиторием:
#   вернуть status="error" с сообщением, что Tool нужно запускать
#   из Git-репозитория.
#
# - при scope="staged" нет подготовленных к коммиту файлов:
#   это НЕ ошибка.
#   Вернуть:
#   {
#       "status": "ok",
#       "scope": "staged",
#       "safe_to_commit": true,
#       "checked_files": 0,
#       "issues_count": 0,
#       "issues": []
#   }
#
# - бинарный файл:
#   не пытаться искать секреты и merge-маркеры внутри содержимого,
#   но проверить его путь и размер.
#
# - файл невозможно прочитать:
#   добавить проблему типа "read_error" в issues вместо выбрасывания
#   необработанного исключения.
#
# - .env.example:
#   не считать запрещённым файлом только из-за имени .env,
#   но его содержимое всё равно проверить на случай случайно вставленного
#   настоящего секрета.
#
# - пустой список проблем:
#   это успешный результат, а не ошибка.


import json
import re
import subprocess
from pathlib import Path

from crewai.tools import tool

def _fail(message: str) -> str:
    """Возвращает ошибку в едином формате."""
    return json.dumps(
        {
            "status": "error",
            "message": message,
        },
        ensure_ascii=False,
    )


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Неизвестная ошибка Git")

    return result.stdout

UNWANTED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
}

UNWANTED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

UNWANTED_SUFFIXES = {
    ".pyc",
    ".log",
    ".tmp",
}

SENSITIVE_NAMES = {
    ".env",
    "credentials.json",
    "id_rsa",
}

SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
}

SECRET_PATTERNS = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "Обнаружен возможный приватный ключ",
    ),
    (
        "api_key",
        re.compile(
            r"""(?i)(api[_-]?key|access[_-]?token|secret[_-]?key)
            \s*[:=]\s*['"][^'"]{8,}['"]""",
            re.VERBOSE,
        ),
        "Обнаружен возможный API-ключ или токен",
    ),
    (
        "password",
        re.compile(
            r"""(?i)password\s*[:=]\s*['"][^'"]+['"]""",
            re.VERBOSE,
        ),
        "Обнаружен возможный пароль",
    ),
]


def _is_binary(data: bytes) -> bool:
    return b"\x00" in data[:4096]


@tool("check_commit_safety")
def check_commit_safety(
    scope: str = "staged",
    max_file_size_kb: int = 1024,
) -> str:
    """Проверяет Git-проект перед коммитом на потенциально опасные файлы.

    Используй этот инструмент, когда пользователь просит проверить проект
    перед коммитом или убедиться, что в Git не попадут секреты, служебные
    файлы, временные каталоги, слишком большие файлы или незавершённые
    merge-конфликты.

    Инструмент только анализирует проект и ничего не удаляет и не изменяет.

    Args:
        scope: область проверки. Допустимые значения:
            'staged' — только файлы, подготовленные через git add;
            'all_tracked' — все файлы, отслеживаемые Git.
        max_file_size_kb: максимальный допустимый размер файла
            в килобайтах, от 1 до 10240. По умолчанию 1024.

    Returns:
        JSON-строка.

        При успешной проверке:
        {
            "status": "ok",
            "safe_to_commit": true,
            "checked_files": 5,
            "issues_count": 0,
            "issues": []
        }

        Если найдены проблемы, status остаётся "ok",
        но safe_to_commit становится false.

        При ошибке самого инструмента:
        {
            "status": "error",
            "message": "..."
        }
    """

    allowed_scopes = {"staged", "all_tracked"}

    if scope not in allowed_scopes:
        return _fail(
            "scope должен быть 'staged' или 'all_tracked', "
            f"получено '{scope}'"
        )

    if not 1 <= max_file_size_kb <= 10240:
        return _fail(
            "max_file_size_kb должен быть от 1 до 10240, "
            f"получено {max_file_size_kb}"
        )

    try:
        # Проверяем, что запускаемся внутри Git-репозитория.
        inside_repo = _run_git(
            "rev-parse",
            "--is-inside-work-tree",
        ).strip()

        if inside_repo != "true":
            return _fail(
                "Текущая директория не является Git-репозиторием"
            )

        repo_root = Path(
            _run_git("rev-parse", "--show-toplevel").strip()
        )

        # Получаем список файлов.
        if scope == "staged":
            output = _run_git(
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACMR",
            )
        else:
            output = _run_git("ls-files")

        files = [
            line.strip()
            for line in output.splitlines()
            if line.strip()
        ]

        issues = []

        for relative_path in files:
            path = Path(relative_path)
            path_parts = set(path.parts)

            # Проверка нежелательных каталогов.
            unwanted_parts = path_parts & UNWANTED_PARTS

            if unwanted_parts:
                issues.append(
                    {
                        "type": "unwanted_file",
                        "severity": "warning",
                        "path": relative_path,
                        "line": None,
                        "message": (
                            "Файл находится в нежелательном каталоге: "
                            + ", ".join(sorted(unwanted_parts))
                        ),
                    }
                )

            # Проверка имени файла.
            if (
                path.name in UNWANTED_NAMES
                or path.suffix.lower() in UNWANTED_SUFFIXES
            ):
                issues.append(
                    {
                        "type": "unwanted_file",
                        "severity": "warning",
                        "path": relative_path,
                        "line": None,
                        "message": (
                            "Этот файл обычно не следует "
                            "добавлять в репозиторий"
                        ),
                    }
                )

            # Проверка потенциально чувствительных файлов.
            sensitive = (
                path.name in SENSITIVE_NAMES
                or path.suffix.lower() in SENSITIVE_SUFFIXES
            )

            # .env.example разрешён.
            if path.name == ".env.example":
                sensitive = False

            if sensitive:
                issues.append(
                    {
                        "type": "sensitive_file",
                        "severity": "critical",
                        "path": relative_path,
                        "line": None,
                        "message": (
                            "Потенциально чувствительный файл "
                            "не следует публиковать"
                        ),
                    }
                )

            try:
                # Для staged читаем именно версию из Git index,
                # то есть то, что реально попадёт в коммит.
                if scope == "staged":
                    content = subprocess.run(
                        ["git", "show", f":{relative_path}"],
                        capture_output=True,
                        check=False,
                    )

                    if content.returncode != 0:
                        raise RuntimeError(
                            content.stderr.decode(
                                "utf-8",
                                errors="replace",
                            ).strip()
                        )

                    data = content.stdout

                else:
                    full_path = repo_root / relative_path
                    data = full_path.read_bytes()

                # Проверка размера.
                size_kb = len(data) / 1024

                if size_kb > max_file_size_kb:
                    issues.append(
                        {
                            "type": "large_file",
                            "severity": "warning",
                            "path": relative_path,
                            "line": None,
                            "message": (
                                f"Размер файла {size_kb:.1f} КБ "
                                f"превышает лимит "
                                f"{max_file_size_kb} КБ"
                            ),
                        }
                    )

                # Бинарные файлы дальше не анализируем.
                if _is_binary(data):
                    continue

                text = data.decode(
                    "utf-8",
                    errors="replace",
                )

                lines = text.splitlines()

                for line_number, line in enumerate(
                    lines,
                    start=1,
                ):
                    # Merge conflict.
                    if line.startswith(
                        ("<<<<<<<", "=======", ">>>>>>>")
                    ):
                        issues.append(
                            {
                                "type": "merge_conflict",
                                "severity": "critical",
                                "path": relative_path,
                                "line": line_number,
                                "message": (
                                    "Обнаружен незавершённый "
                                    "merge-конфликт"
                                ),
                            }
                        )

                    # Потенциальные секреты.
                    for _, pattern, message in SECRET_PATTERNS:
                        if pattern.search(line):
                            issues.append(
                                {
                                    "type": "secret",
                                    "severity": "critical",
                                    "path": relative_path,
                                    "line": line_number,
                                    "message": message,
                                }
                            )

            except Exception as exc:
                issues.append(
                    {
                        "type": "read_error",
                        "severity": "warning",
                        "path": relative_path,
                        "line": None,
                        "message": (
                            "Не удалось проверить файл: "
                            f"{exc}"
                        ),
                    }
                )

        return json.dumps(
            {
                "status": "ok",
                "scope": scope,
                "safe_to_commit": len(issues) == 0,
                "checked_files": len(files),
                "issues_count": len(issues),
                "issues": issues,
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        return _fail(
            f"Не удалось проверить проект: {exc}"
        )