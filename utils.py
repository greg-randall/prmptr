# utils.py
import re
from typing import Dict, List, Set

# A special node name that represents the initial user input.
# This is treated as a starting point and not a prompt to be generated.
INPUT_NODE_NAME = "input text"


def parse_prompt_file(file_content: str) -> Dict[str, str]:
    """
    Parses a prompt file and extracts all named variable definitions.

    This function finds all occurrences of '[[variable_name]] =' and treats
    the text that follows (until the next definition) as the content for that
    variable.

    Args:
        file_content: The complete string content of the prompt file.

    Returns:
        A dictionary mapping each variable name to its prompt content.
    """
    # This regex finds the start of each variable definition.
    # It's compiled for efficiency if this function were called many times.
    definition_re = re.compile(r'\[\[(.+?)\]\]\s*=', re.MULTILINE)
    prompt_definitions = {}

    # Find all definition markers in the file.
    matches = list(definition_re.finditer(file_content))

    # Iterate through the matches to slice out the content for each one.
    for i, match in enumerate(matches):
        # Group 1 of the regex captures the variable name inside [[ ]].
        name = match.group(1).strip()

        # The content for this variable starts after the '=' of the current match.
        content_start = match.end()

        # The content ends at the start of the *next* match.
        # If it's the last match, the content runs to the end of the file.
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(file_content)

        content = file_content[content_start:content_end].strip()
        prompt_definitions[name] = content

    return prompt_definitions


def find_dependencies(prompt_text: str) -> List[str]:
    """
    Finds all [[dependency]] placeholders within a given text.

    Args:
        prompt_text: The text of a single prompt.

    Returns:
        A list of all dependency names found in the text.
    """
    return re.findall(r'\[\[([^\]]+)\]\]', prompt_text)


def build_dependency_graph(prompt_definitions: Dict[str, str]) -> Dict[str, List[str]]:
    """
    Builds a graph representing which variables depend on others.

    This is a more Pythonic version of the original function, using a
    dictionary comprehension for a concise and readable implementation.

    Args:
        prompt_definitions: The dictionary of variable names to prompt templates.

    Returns:
        A dictionary where each key is a variable name and the value is a list
        of its dependencies.
    """
    return {
        name: find_dependencies(text)
        for name, text in prompt_definitions.items()
    }


def resolve_execution_order(graph: Dict[str, List[str]]) -> List[str]:
    """
    Determines the correct execution order using a topological sort.

    This function performs a depth-first search (DFS) starting from the
    'output' node to ensure all its dependencies are resolved first,
    avoiding circular references.

    Args:
        graph: The dependency graph.

    Returns:
        A list of variable names in the order they should be executed.

    Raises:
        ValueError: If no 'output' node is defined or a circular dependency
                    is detected.
    """
    if 'output' not in graph:
        raise ValueError("The prompt file must contain an [[output]] variable.")

    order: List[str] = []
    visiting: Set[str] = set()  # For detecting cycles (A -> B -> A).
    visited: Set[str] = set()   # For tracking already processed nodes.

    def visit(node: str):
        """Recursively visit a node to perform the depth-first search."""
        # If we have already processed this node, we're done with it.
        if node in visited:
            return
        # If we encounter a node that is currently in our recursion stack,
        # we have found a circular dependency.
        if node in visiting:
            raise ValueError(f"Circular dependency detected involving '[[{node}]]'.")

        # INPUT_NODE_NAME is a special case; it has no dependencies to resolve.
        if node in graph:
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)

        visited.add(node)
        # Only add nodes that are actual prompts (not the initial input) to the
        # final execution order list.
        if node in graph:
            order.append(node)

    # Start the entire process from the 'output' node.
    visit('output')
    return order