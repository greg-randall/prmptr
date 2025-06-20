# prmptr.py
import os
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from openai import OpenAI
from utils import (
    INPUT_NODE_NAME,
    parse_prompt_file,
    build_dependency_graph,
    resolve_execution_order,
)

# --- Configuration ---
# Using constants makes the code cleaner and easier to modify.
MODEL_NAME = "gpt-4o-mini"
SYSTEM_PROMPT = "You are a helpful assistant. Please follow the instructions exactly."


def call_llm(client: OpenAI, prompt: str) -> str | None:
    """
    Sends a prompt to the OpenAI API and returns the response.

    Args:
        client: The configured OpenAI client instance.
        prompt: The complete prompt to send to the model.

    Returns:
        The text content from the AI's response, or None if an error occurs.
    """
    try:
        print("Sending prompt to LLM...")
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        print("...LLM response received.")
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"An error occurred while calling the API: {e}")
        return None


def execute_prompt_chain(
    client: OpenAI,
    order: List[str],
    definitions: Dict[str, str],
    graph: Dict[str, List[str]],
    initial_input: str,
) -> tuple[str, str] | None:
    """
    Executes the planned prompt chain step-by-step.

    Args:
        client: The OpenAI client.
        order: The list of variable names in the correct execution order.
        definitions: The dictionary mapping variable names to their templates.
        graph: The dependency graph for the prompts.
        initial_input: The initial text to start the chain with.

    Returns:
        A tuple containing the final output string and the full log string,
        or None if the process fails.
    """
    resolved_values = {INPUT_NODE_NAME: initial_input}
    log_entries = []

    for name in order:
        print(f"\n--- Resolving: [[{name}]] ---")

        template = definitions[name]
        dependencies = graph.get(name, [])

        # If a node has no dependencies, treat it as a static variable
        # and do not call the LLM.
        if not dependencies:
            print(f"Node '[[{name}]]' is static. Using its content directly.")
            result = template
            resolved_values[name] = result
            log_entries.append(
                f"--- Step: [[{name}]] (Static) ---\n\n"
                f"CONTENT USED DIRECTLY:\n---\n{result}\n---\n"
            )
            continue

        # This is a dynamic prompt; resolve its dependencies and call the LLM.
        prompt = template
        for dep in dependencies:
            if dep not in resolved_values:
                print(f"Error: Could not find value for dependency [[{dep}]].")
                return None
            prompt = prompt.replace(f"[[{dep}]]", resolved_values[dep])

        result = call_llm(client, prompt)
        if result is None:
            print(f"Failed to resolve [[{name}]]. Aborting.")
            return None

        resolved_values[name] = result
        log_entries.append(
            f"--- Step: [[{name}]] ---\n\n"
            f"PROMPT SENT TO LLM:\n---\n{prompt}\n---\n\n"
            f"RESPONSE RECEIVED:\n---\n{result}\n---\n"
        )

    final_output = resolved_values.get("output", "Error: Final output not generated.")
    full_log = "\n\n====================\n\n".join(log_entries)

    return final_output, full_log


def main():
    """
    Main function to orchestrate the prompt chaining process.
    """
    parser = argparse.ArgumentParser(
        description="Process a prompt chain file against an input text file."
    )
    parser.add_argument("prompt_file", help="Path to the prompt chain file.")
    parser.add_argument("input_file", help="Path to the input text file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    args = parser.parse_args()

    # --- 1. Setup and File Reading ---
    prompt_file_path = Path(args.prompt_file)
    input_file_path = Path(args.input_file)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: The OPENAI_API_KEY environment variable is not set.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    try:
        prompt_content = prompt_file_path.read_text(encoding='utf-8')
        input_content = input_file_path.read_text(encoding='utf-8')
    except FileNotFoundError as e:
        print(f"Error: Could not find a file - {e}")
        sys.exit(1)

    # --- 2. Parsing and Dependency Resolution ---
    print("Parsing prompt file and resolving dependencies...")
    definitions = parse_prompt_file(prompt_content)
    graph = build_dependency_graph(definitions)

    if args.debug:
        print("\n--- DEBUG: Parsed Prompt Definitions ---")
        for name, text in definitions.items():
            print(f"  [[{name}]] = {repr(text)}")
        print("\n--- DEBUG: Dependency Graph ---")
        for name, deps in graph.items():
            print(f"  '{name}' depends on: {deps}")
        print("-" * 30)

    try:
        execution_order = resolve_execution_order(graph)
        print(f"\nExecution order determined: {execution_order}")
    except ValueError as e:
        print(f"\nError resolving execution order: {e}")
        sys.exit(1)

    # --- 3. Executing the Chain ---
    results = execute_prompt_chain(
        client, execution_order, definitions, graph, input_content
    )

    if results is None:
        print("\nProcessing failed. No output files will be written.")
        sys.exit(1)

    final_output, full_log = results

    # --- 4. Writing Output Files ---
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"{timestamp}_{input_file_path.name}_promptchain.log"
    output_filename = f"{timestamp}_{input_file_path.name}_output.txt"

    try:
        Path(log_filename).write_text(full_log, encoding='utf-8')
        Path(output_filename).write_text(final_output, encoding='utf-8')

        print("\n===================================")
        print("        PROCESSING COMPLETE")
        print("===================================\n")
        print(f"Full log written to:    {log_filename}")
        print(f"Final output written to: {output_filename}")

    except IOError as e:
        print(f"Error writing output files: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()