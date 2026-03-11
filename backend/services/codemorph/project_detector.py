"""
Project type detection for CodeMorph.
Scans for build files to determine project type and build/test commands.
"""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Project type definitions: (marker_file, project_type, build_command, test_command)
PROJECT_TYPES = [
    ("pom.xml", "maven", "mvn clean package -DskipTests", "mvn test"),
    ("build.gradle", "gradle", "./gradlew build -x test", "./gradlew test"),
    ("build.gradle.kts", "gradle", "./gradlew build -x test", "./gradlew test"),
    ("package.json", "npm", "npm install && npm run build", "npm test"),
    ("requirements.txt", "python", "pip install -r requirements.txt", "pytest"),
    ("pyproject.toml", "python", "pip install -e .", "pytest"),
    ("Cargo.toml", "rust", "cargo build", "cargo test"),
    ("go.mod", "go", "go build ./...", "go test ./..."),
    ("Makefile", "make", "make", "make test"),
]


def detect_project_type(project_dir: str) -> Dict[str, Any]:
    """
    Detect project type by scanning for build system marker files.

    Args:
        project_dir: Path to the project directory

    Returns:
        Dictionary with project_type, build_command, test_command, file_count, complexity
    """
    detected_type = "unknown"
    build_command = None
    test_command = None

    for marker_file, proj_type, build_cmd, test_cmd in PROJECT_TYPES:
        if os.path.exists(os.path.join(project_dir, marker_file)):
            detected_type = proj_type
            build_command = build_cmd
            test_command = test_cmd
            break

    # Also check for .csproj files (.NET)
    for f in os.listdir(project_dir) if os.path.isdir(project_dir) else []:
        if f.endswith(".csproj"):
            detected_type = "dotnet"
            build_command = "dotnet build"
            test_command = "dotnet test"
            break

    # Count files for complexity estimation
    file_count = 0
    try:
        for root, dirs, files in os.walk(project_dir):
            # Skip hidden dirs and common non-source dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'target', 'build', 'dist', '__pycache__', '.git')]
            file_count += len(files)
    except Exception:
        pass

    # Complexity estimation
    if file_count > 500:
        complexity = "high"
    elif file_count > 100:
        complexity = "medium"
    else:
        complexity = "low"

    result = {
        "project_type": detected_type,
        "build_command": build_command,
        "test_command": test_command,
        "file_count": file_count,
        "complexity": complexity,
    }

    logger.info(f"Detected project type: {result}")
    return result
