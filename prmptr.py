# prmptr.py
import os
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import asyncio
import concurrent.futures
from collections import defaultdict
import multiprocessing

from openai import OpenAI
from utils import (
    INPUT_NODE_NAME,
    parse_prompt_file,
    build_dependency_graph,
    resolve_execution_order,
    find_parallel_groups,
)
from logging_config import setup_logging, get_logger, log_with_extra, cleanup_old_logs

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
        logger.info("Sending prompt to LLM...", extra={'model': MODEL_NAME, 'prompt_length': len(prompt)})
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        response_content = response.choices[0].message.content.strip()
        logger.info("LLM response received", extra={'response_length': len(response_content)})
        return response_content
    except Exception as e:
        logger.error(f"An error occurred while calling the API: {e}", exc_info=True)
        return None


def execute_prompt_chain_parallel(
    client: OpenAI,
    parallel_groups: List[List[str]],
    definitions: Dict[str, str],
    graph: Dict[str, List[str]],
    initial_input: str,
    max_workers: int = None,
) -> tuple[str, str] | None:
    """
    Executes the planned prompt chain with parallel execution for independent prompts.

    Args:
        client: The OpenAI client.
        parallel_groups: Groups of prompts that can be executed in parallel.
        definitions: The dictionary mapping variable names to their templates.
        graph: The dependency graph for the prompts.
        initial_input: The initial text to start the chain with.
        max_workers: Maximum number of worker threads. Defaults to 2x CPU cores.

    Returns:
        A tuple containing the final output string and the full log string,
        or None if the process fails.
    """
    resolved_values = {INPUT_NODE_NAME: initial_input}
    log_entries = []
    
    # Set default max_workers to 2x CPU cores if not specified
    if max_workers is None:
        max_workers = multiprocessing.cpu_count() * 2
        
    logger.info(f"Using {max_workers} worker threads for parallel execution")

    def process_single_prompt(name: str) -> tuple[str, str] | None:
        """Process a single prompt and return (name, result, log_entry) or None if failed."""
        logger.info(f"Resolving prompt variable: [[{name}]]")
        
        template = definitions[name]
        dependencies = graph.get(name, [])

        # If a node has no dependencies, treat it as a static variable
        if not dependencies:
            logger.debug(f"Node '[[{name}]]' is static. Using its content directly.")
            result = template
            log_entry = (
                f"--- Step: [[{name}]] (Static) ---\n\n"
                f"CONTENT USED DIRECTLY:\n---\n{result}\n---\n"
            )
            return name, result, log_entry

        # This is a dynamic prompt; resolve its dependencies and call the LLM.
        prompt = template
        for dep in dependencies:
            if dep not in resolved_values:
                logger.error(f"Could not find value for dependency [[{dep}]]", extra={'missing_dependency': dep, 'current_node': name})
                return None
            prompt = prompt.replace(f"[[{dep}]]", resolved_values[dep])

        result = call_llm(client, prompt)
        if result is None:
            logger.error(f"Failed to resolve [[{name}]]. Aborting.", extra={'failed_node': name})
            return None

        log_entry = (
            f"--- Step: [[{name}]] ---\n\n"
            f"PROMPT SENT TO LLM:\n---\n{prompt}\n---\n\n"
            f"RESPONSE RECEIVED:\n---\n{result}\n---\n"
        )
        return name, result, log_entry

    # Process each group in sequence, but prompts within each group in parallel
    for group in parallel_groups:
        if len(group) == 1:
            # Single prompt - no need for parallel processing
            result = process_single_prompt(group[0])
            if result is None:
                return None
            name, value, log_entry = result
            resolved_values[name] = value
            log_entries.append(log_entry)
        else:
            # Multiple prompts - execute in parallel
            logger.info(f"Executing {len(group)} prompts in parallel: {group}")
            
            # Use the smaller of max_workers or group size to avoid unnecessary threads
            workers_for_group = min(max_workers, len(group))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers_for_group) as executor:
                # Submit all prompts in the group
                future_to_name = {
                    executor.submit(process_single_prompt, name): name 
                    for name in group
                }
                
                # Collect results
                group_results = []
                for future in concurrent.futures.as_completed(future_to_name):
                    result = future.result()
                    if result is None:
                        return None
                    group_results.append(result)
                
                # Sort results by original order for consistent logging
                group_results.sort(key=lambda x: group.index(x[0]))
                
                # Update resolved values and log entries
                for name, value, log_entry in group_results:
                    resolved_values[name] = value
                    log_entries.append(log_entry)

    final_output = resolved_values.get("output", "Error: Final output not generated.")
    full_log = "\n\n====================\n\n".join(log_entries)

    return final_output, full_log


def execute_prompt_chain(
    client: OpenAI,
    order: List[str],
    definitions: Dict[str, str],
    graph: Dict[str, List[str]],
    initial_input: str,
) -> tuple[str, str] | None:
    """
    Executes the planned prompt chain step-by-step (sequential fallback).

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
        logger.info(f"Resolving prompt variable: [[{name}]]")

        template = definitions[name]
        dependencies = graph.get(name, [])

        # If a node has no dependencies, treat it as a static variable
        # and do not call the LLM.
        if not dependencies:
            logger.debug(f"Node '[[{name}]]' is static. Using its content directly.")
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
                logger.error(f"Could not find value for dependency [[{dep}]]", extra={'missing_dependency': dep, 'current_node': name})
                return None
            prompt = prompt.replace(f"[[{dep}]]", resolved_values[dep])

        result = call_llm(client, prompt)
        if result is None:
            logger.error(f"Failed to resolve [[{name}]]. Aborting.", extra={'failed_node': name})
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
    global logger
    
    parser = argparse.ArgumentParser(
        description="Process a prompt chain file against an input text file."
    )
    parser.add_argument("prompt_file", help="Path to the prompt chain file.")
    parser.add_argument("input_file", help="Path to the input text file.")
    parser.add_argument("--debug", action="store_true", help="Enable debug output.")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                       default="INFO", help="Set the logging level (default: INFO)")
    parser.add_argument("--log-file", help="Path to log file (default: auto-generated)")
    parser.add_argument("--json-logs", action="store_true", help="Use JSON format for file logs")
    parser.add_argument("--no-console", action="store_true", help="Disable console output")
    parser.add_argument("--no-parallel", action="store_true", help="Disable parallel execution (use sequential)")
    parser.add_argument("--max-workers", type=int, help="Maximum number of worker threads for parallel execution (default: 2x CPU cores)")
    args = parser.parse_args()
    
    # Set up logging based on command line arguments
    log_level = "DEBUG" if args.debug else args.log_level
    logger = setup_logging(
        log_level=log_level,
        log_file=args.log_file,
        json_format=args.json_logs,
        console_output=not args.no_console
    )
    
    # Clean up old logs periodically
    cleanup_old_logs()

    # --- 1. Setup and File Reading ---
    prompt_file_path = Path(args.prompt_file)
    input_file_path = Path(args.input_file)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.critical("The OPENAI_API_KEY environment variable is not set.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    try:
        prompt_content = prompt_file_path.read_text(encoding='utf-8')
        input_content = input_file_path.read_text(encoding='utf-8')
        logger.info("Successfully loaded input files", extra={
            'prompt_file': str(prompt_file_path),
            'input_file': str(input_file_path),
            'prompt_size': len(prompt_content),
            'input_size': len(input_content)
        })
    except FileNotFoundError as e:
        logger.critical(f"Could not find a file - {e}", exc_info=True)
        sys.exit(1)

    # --- 2. Parsing and Dependency Resolution ---
    logger.info("Parsing prompt file and resolving dependencies...")
    definitions = parse_prompt_file(prompt_content)
    graph = build_dependency_graph(definitions)
    logger.debug("Dependency analysis complete", extra={
        'num_definitions': len(definitions),
        'definitions': list(definitions.keys())
    })

    if args.debug:
        logger.debug("Parsed prompt definitions:", extra={'definitions': {name: text[:100] + '...' if len(text) > 100 else text for name, text in definitions.items()}})
        logger.debug("Dependency graph:", extra={'dependencies': graph})

    try:
        execution_order = resolve_execution_order(graph)
        logger.info("Execution order determined", extra={'execution_order': execution_order})
    except ValueError as e:
        logger.critical(f"Error resolving execution order: {e}", exc_info=True)
        sys.exit(1)

    # --- 3. Executing the Chain ---
    if args.no_parallel:
        logger.info("Using sequential execution mode")
        results = execute_prompt_chain(
            client, execution_order, definitions, graph, input_content
        )
    else:
        # Use parallel execution
        parallel_groups = find_parallel_groups(graph)
        logger.info(f"Using parallel execution mode with {len(parallel_groups)} groups", 
                   extra={'parallel_groups': parallel_groups})
        results = execute_prompt_chain_parallel(
            client, parallel_groups, definitions, graph, input_content, args.max_workers
        )

    if results is None:
        logger.critical("Processing failed. No output files will be written.")
        sys.exit(1)

    final_output, full_log = results

    # --- 4. Writing Output Files ---
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"{timestamp}_{input_file_path.name}_promptchain.log"
    output_filename = f"{timestamp}_{input_file_path.name}_output.txt"

    try:
        Path(log_filename).write_text(full_log, encoding='utf-8')
        Path(output_filename).write_text(final_output, encoding='utf-8')

        logger.info("Processing completed successfully", extra={
            'execution_log_file': log_filename,
            'output_file': output_filename,
            'final_output_length': len(final_output)
        })
        
        # Also print to console for user visibility
        if not args.no_console:
            print("\n===================================")
            print("        PROCESSING COMPLETE")
            print("===================================\n")
            print(f"Full log written to:    {log_filename}")
            print(f"Final output written to: {output_filename}")

    except IOError as e:
        logger.critical(f"Error writing output files: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()