from io import StringIO
from pathlib import Path
import string
from typing import Final
from textwrap import dedent
from importlib import resources
from pygit2.repository import Repository

from autocommit.commands import commands, diff_all_files
from autocommit.build_ragdb import get_project_ragdb
from mistral_tools.conversation import ModelConversation
from mistral_tools.utils import RateLimiter


def get_prompt(prompt_file):
    """Load a prompt from a resource file"""
    resource_files = resources.files("autocommit.mistral_model")
    prompts = resource_files / "prompts"
    lines = (prompts / prompt_file).read_text().splitlines()
    lines = [l for l in lines if not l.startswith("#")] # remove comments
    return "\n".join(lines)

def says_ready(content):
    """Check if the model says it is ready (for use with tool calling)"""
    if not content: return False
    last_line: str = content.splitlines()[-1]
    last_line = last_line.strip()
    last_line = last_line.translate({c: None for c in string.punctuation})
    last_line = last_line.lower()
    return last_line == "ready"

def get_initial_prompt(include_diff=False, rag=False, *, 
                       repository: Repository, repo_path, n_context_chunks = 10, 
                       api_key, rate_limit):
    """Get the initial prompt for the model"""
    start_prompt: str = get_prompt("start_prompt.txt")
    s = StringIO()
    diff_value = None
    if rag:
        if diff_value is None: # get the diff if we haven't already
            diff_value = diff_all_files(repository=repository)
        rag_db = get_project_ragdb(Path(repo_path), rate_limit=rate_limit)
        rag_prompt = dedent(f"""
            Here are the changes in the codebase:
            <diff>
            {diff_value}
            </diff>
            What are the most relevant parts of the codebase 
            that I should consider to understand these changes?
            In particular, important parts of the readme, 
            and definitions of functions or classes that are called in this code.
            """)
        chunks, _ = rag_db.query(rag_prompt, n_results=n_context_chunks, 
                                 api_key=api_key)
        s.write("\n Here is some relevant context:\n<context>\n")
        for chunk in chunks:
            if not chunk.text_chunk.strip(): continue # skip empty chunks
            s.write(chunk.to_str())
            s.write("\n")
        s.write("</context>\n")
    s.write(start_prompt)
    if include_diff:
        if diff_value is None:
            diff_value = diff_all_files(repository=repository)
        s.write("<diff>\n")
        s.write(diff_value)
        s.write("\n</diff>")
    return s.getvalue()


def fix_formatting(content):
    """Fix formatting issues in the result.

    Despite my best effort in prompt engineering,
    the model keeps messing up the format
    of the commit message.
    """
    # remove extra newlines
    content = content.strip()
    content = content.replace("\n\n\n", "\n\n")
    
    # fix title formatting
    lines = content.splitlines()
    if len(lines) < 1:
        return content
    potential_prefixes = ["Title:", "Commit message:", "Body:", "Body"]
    for num_line in range(len(lines)):
        line = lines[num_line]
        for prefix in potential_prefixes:
            if line.lower().startswith(prefix.lower()):
                line = line[len(prefix):]
        lines[num_line] = line
    title, *body= lines
    title = title.strip()

    title = title.strip('": ') # the model sometimes adds quotes around the title
    # remove newlines at beginnig of body, I'll re-add them later
    start_body = 0
    while start_body < len(body) and body[start_body].strip() == "":
        start_body += 1
    body = body[start_body:]
    if not body:
        body = ["# no body"]

    body_str = "\n".join(body)
    return f"{title}\n\n{body_str}"



def main(api_key, repo_path, max_tool_uses=10, use_tools=False, 
         use_rag=True, separate_title_body=False):
    """Generate a commit message"""
    repo = Repository(str(repo_path))
    if use_rag:
        commands_bound = commands.bind(repository=repo)
    else: commands_bound = None

    rate_limit = RateLimiter(2)

    system_prompt: Final[str] = get_prompt("system_prompt.txt")
    prompt: Final[str] = get_prompt("exchange_prompt.txt")
    title_prompt: Final[str] = get_prompt("title_prompt.txt")
    final_prompt: Final[str] = get_prompt("final_prompt.txt")
    not_separated_prompt: Final[str] = get_prompt("not_separated_prompt.txt")
    # final_prompt: Final[str] = get_prompt("final_prompt.txt")

    # TODO possibliy prefix? to handle getting title and body
    # also dummy too calls for information that will definitely be useful

    model: Final[str] = "codestral-latest"

    conversation = ModelConversation(
            model=model, api_key=api_key, tool_register=commands_bound, 
            system_prompt=system_prompt, rate_limit=rate_limit)

    start_prompt = get_initial_prompt(include_diff=True, rag=use_rag, 
        repository=repo, repo_path=repo_path, api_key=api_key, rate_limit=rate_limit)

    if use_tools:
        conversation.add_message(start_prompt)
        response = conversation.send(tool_choice="any" if use_tools else "none")
        n_remaining_tool_uses = max_tool_uses - 1

        while n_remaining_tool_uses > 1:
            # conversation.add_message(prompt)
            response = conversation.send(tool_choice="auto")
            n_remaining_tool_uses -= 1
            if says_ready(response.message.content):
                break
            elif not response.message.tool_calls:
                conversation.add_message(prompt)

        conversation.add_message(title_prompt if separate_title_body else not_separated_prompt)
    else: 
        conversation.add_message(start_prompt + "\n" + (title_prompt if separate_title_body else not_separated_prompt))

    if separate_title_body:
        conversation.add_prefix("Title: ")
        response_title = conversation.send(tool_choice="none")
        conversation.add_message(final_prompt)
        conversation.add_prefix("Body: ")
        response_body = conversation.send(tool_choice="none")

        title = response_title.message.content
        body = response_body.message.content
        result = f"{title}\n\n{body}"
    else:
        conversation.add_prefix("Commit message: ")
        response_title = conversation.send(tool_choice="none")
        result = response_title.message.content

    return fix_formatting(result)
