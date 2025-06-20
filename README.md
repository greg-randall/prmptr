# Prmptr: A Sophisticated Prompt Chaining Engine

Prmptr is a powerful command-line tool designed to execute complex, multi-step workflows using Large Language Models (LLMs). It allows you to define a chain of interconnected prompts where the output of one step can be used as the input for another. This enables the creation of sophisticated pipelines for tasks like research analysis, structured drafting, and stylistic rewriting, all automated through a single command.

## Quick Start

Let's run through a practical example. We'll take a raw news clipping and run it through a three-stage pipeline to create a social media post:

1.  **Extraction:** Pull out a summary and key entities in parallel.
2.  **Drafting:** Use the summary and keywords to create an initial draft for a Mastodon post.
3.  **Refinement:** Pass the draft to a final "cleanup" prompt to ensure it's ready for publishing.

**1. Create a prompt chain file named `generate-social.txt`:**

```
[[output]] =
Make sure this post has the right tone for Mastodon and is under 500 characters. Reply just with the updated post, no explanation!
[[draft_post]]

[[draft_post]] =
You are a social media manager for a tech news account on Mastodon. Based on the summary below, write a compelling post. Convert the extracted keywords into 3-4 relevant hashtags.

Summary:
[[summary]]

Keywords:
[[keywords]]

[[keywords]] =
List the key people, organizations, and locations from the article below.
Article: [[input text]]

[[summary]] =
Summarize the following article in one sentence.
Article: [[input text]]
```

**2. Create an input file named `article.txt`:**

```
London, UK – The Ministry of Innovation has awarded a £50 million grant to QuantumLeap, a startup founded by Dr. Aris Thorne, to build the nation's first commercially viable quantum computer. The project, based in Manchester, aims to deliver a 1,000-qubit machine within three years, positioning the UK as a global leader in the field. "This investment secures our future in a transformative technology," said Minister Eva Rostova.
```

**3. Run the command:**

```bash
python prmptr.py generate-social.txt article.txt
```

That's it! The script will execute the chain on the article. It will extract the key entities, summarize the news, draft a compelling post about the UK's investment in quantum computing, and then give it a final polish for Mastodon before saving the result.

## Who is this for?

This tool is for anyone who wants to leverage the power of LLMs for more than just simple, one-shot questions. It's perfect for:

* **Writers & Journalists:** Automate the process of turning raw research notes into a structured draft and then into a polished, stylized article.
* **Researchers:** Create pipelines to summarize, analyze, and synthesize information from multiple sources in a consistent and repeatable way.
* **Content Creators:** Build workflows to generate different formats of content (e.g., a blog post, a Mastodon post, and a summary) from a single source of input.
* **Developers & Hobbyists:** Experiment with complex LLM interactions and build sophisticated text-generation systems without getting bogged down in boilerplate API code.

## Why is it Cool?

Prmptr isn't just another API wrapper. Its strength lies in its ability to manage dependencies and execute a logical sequence of prompts.

* **Dependency Management:** The script automatically detects dependencies between your prompts. If your `[[draft_post]]` prompt needs both `[[summary]]` and `[[keywords]]`, Prmptr resolves them first before generating the post.
* **Static & Dynamic Steps:** You can define both static variables (like a style guide) that are directly injected and dynamic variables that require an LLM call to be resolved. The script is smart enough to not send static content to the API, saving time and tokens.
* **Clear & Reusable Workflows:** By defining your entire workflow in a single "prompt chain" file, you create a reusable and easy-to-understand recipe. You can run the same complex process on different input files with ease.
* **Full Transparency:** The tool generates a detailed `.log` file for every run. This log shows you the exact prompt sent to the LLM and the raw response received at every single step, making it easy to debug and refine your chains.

## How to Use It

### 1. Setup

First, make sure you have Python and the required library installed.

```bash
pip install openai
```

Next, you need to set your OpenAI API key as an environment variable. The script will not work without it.

**On macOS/Linux:**
```bash
export OPENAI_API_KEY="your-api-key-here"
```

**On Windows:**
```bash
set OPENAI_API_KEY="your-api-key-here"
```

### 2. Create a Prompt Chain File

This is a plain text file where you define all the steps in your workflow. The syntax is simple:

`[[variable_name]] =`
`The prompt or content for this variable goes here.`

* **Dependencies:** To use the content of one variable inside another, just include its name in double brackets, like `[[dependency_name]]`.
* **Initial Input:** The script reserves `[[input text]]` as the special variable that holds the content of your input file.
* **Final Output:** You must have a variable named `[[output]]`. This is always the last prompt in the chain and its resolution is what gets saved to the final output file. It's a great place to put a final quality-check or formatting instruction.

### 3. Prepare an Input File

Create a simple text file that will be used as the starting input for the chain (`[[input text]]`).

### 4. Run the Script

Execute the script from your terminal, providing the path to your prompt chain file and your input file.

```bash
python prmptr.py your_prompt_chain.txt your_input_file.txt
```

You can also enable debug mode to see the dependency graph and execution order printed in the console.

```bash
python prmptr.py your_prompt_chain.txt your_input_file.txt --debug
```

### 5. Check the Output

The script generates two timestamped files:

1.  **`..._output.txt`**: This file contains the final result from your `[[output]]` variable.
2.  **`..._promptchain.log`**: This file contains a complete log of the entire process, including the content of static variables and the full LLM prompts and responses for dynamic variables. It is incredibly useful for seeing how the final output was constructed.