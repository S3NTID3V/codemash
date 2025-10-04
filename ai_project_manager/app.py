import streamlit as st
import json
import os
import time
from queue import Queue
import traceback
from gemini_client import get_gemini_client
from repo_monitor import start_monitoring, stop_monitoring

# --- Utility Functions ---

def load_json(filepath: str) -> dict:
    """
    Loads data from a JSON file.
    If the file doesn't exist or is empty/corrupt, it returns an empty dictionary.
    """
    if not os.path.exists(filepath):
        # Create directory if it doesn't exist to avoid errors on first run
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        return {}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_json(data: dict, filepath: str):
    """Saves dictionary data to a JSON file with pretty printing."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

# --- Main Application Logic ---

def main():
    """
    Main function to run the Streamlit application.
    """
    st.set_page_config(page_title="AI Project Manager", layout="wide")
    st.title("🤖 AI Project Manager")

    # --- Data Loading and Session State Initialization ---

    # Load configuration and persistent storage
    config = load_json('ai_project_manager/config.json')
    storage = load_json('ai_project_manager/storage.json')

    # Initialize Streamlit's session state to hold application data across reruns
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'tasks' not in st.session_state:
        st.session_state.tasks = storage.get('tasks', [])
    if 'logs' not in st.session_state:
        st.session_state.logs = storage.get('logs', [])
    if 'notification' not in st.session_state:
        st.session_state.notification = None
    # Thread-safe queue for repository monitoring events
    if 'repo_event_queue' not in st.session_state:
        st.session_state.repo_event_queue = Queue()

    # --- Sidebar for Configuration ---

    st.sidebar.title("Project Controls")
    repo_path = st.sidebar.text_input("Local Repo Path", value=config.get("repo_path", ""))
    api_key = st.sidebar.text_input("Gemini API Key", value=config.get("api_key", ""), type="password")

    if st.sidebar.button("Save Configuration"):
        config['repo_path'] = repo_path
        config['api_key'] = api_key
        save_json(config, 'ai_project_manager/config.json')
        st.sidebar.success("Configuration saved!")
        st.rerun() # Rerun to apply changes immediately

    # --- AI Client Initialization ---

    gemini_client = None
    try:
        gemini_client = get_gemini_client(api_key)
    except ValueError as e:
        st.sidebar.error(f"Failed to initialize AI: {e}")

    # --- Repository Monitoring Setup ---

    if 'repo_observer' not in st.session_state:
        st.session_state.repo_observer = None

    if repo_path and os.path.isdir(repo_path):
        # Start monitoring if the path is valid and not already being monitored
        if st.session_state.get('monitoring_path') != repo_path:
            # Stop any previous observer if the path changes
            if st.session_state.get('repo_observer'):
                stop_monitoring(st.session_state.repo_observer)

            try:
                # Start the watchdog observer in a background thread
                st.session_state.repo_observer = start_monitoring(repo_path, st.session_state.repo_event_queue)
                st.session_state.monitoring_path = repo_path
                st.sidebar.success(f"Monitoring: {os.path.basename(repo_path)}")
                log_event("Repo Monitoring Started", {"path": repo_path})
            except Exception:
                st.sidebar.error(f"Error starting monitor: {traceback.format_exc()}")
    elif repo_path:
        st.sidebar.warning("Invalid repository path.")

    # --- Process Repository Events from Queue ---

    # Check the queue for file change events from the watchdog thread
    while not st.session_state.repo_event_queue.empty():
        event = st.session_state.repo_event_queue.get()
        log_event("Repo Change Detected", event)
        st.session_state.notification = f"Repo change: {event['event_type']} on {os.path.basename(event['src_path'])}"
        st.rerun() # Rerun to display the notification toast

    # --- Main Dashboard UI ---

    st.header("Dashboard")

    # Find the current pending task and the last completed one
    current_task = next((task for task in st.session_state.tasks if task['status'] == 'pending'), None)
    last_completed_task = next((task for task in reversed(st.session_state.tasks) if task['status'] == 'verified'), None)

    col1, col2 = st.columns(2)
    with col1:
        if current_task:
            st.info(f"**Current Task:** {current_task['description']}")
        else:
            st.success("No pending tasks. Ask 'What's next?' to generate a new one.")
    with col2:
        if last_completed_task:
            st.success(f"**Last Completed Task:** {last_completed_task['description']}")

    st.subheader("Milestones")
    if st.session_state.tasks:
        for task in st.session_state.tasks:
            st.markdown(f"- {task['description']} (`{task['status']}`)")
    else:
        st.write("No milestones defined yet.")

    # --- Alerts and Logging ---

    # Display notifications as toasts
    if 'notification' in st.session_state and st.session_state.notification:
        st.toast(st.session_state.notification)
        st.session_state.notification = None  # Clear after showing

    # Display logs in an expandable section
    with st.expander("View Full Event Logs"):
        st.json(st.session_state.logs)

    # --- Chat Interface ---

    st.header("Chat with AI")
    # Display chat history
    for author, message in st.session_state.chat_history:
        with st.chat_message(author):
            st.markdown(message)

    # Get user input from chat box
    user_input = st.chat_input("What would you like to do?")

    if user_input:
        st.session_state.chat_history.append(("user", user_input))
        with st.chat_message("user"):
            st.markdown(user_input)

        # Process user input
        if gemini_client:
            if "what's next" in user_input.lower():
                handle_task_generation(gemini_client)
            elif user_input.lower().startswith("done"):
                handle_task_verification(user_input, gemini_client)
            else:
                # Generic chat response
                prompt = f"User query: '{user_input}'. Previous context: {st.session_state.tasks}"
                ai_response = gemini_client.generate_response(prompt)
                st.session_state.chat_history.append(("assistant", ai_response))
                with st.chat_message("assistant"):
                    st.markdown(ai_response)
        else:
            # Handle case where AI is not configured
            st.session_state.chat_history.append(("assistant", "AI is not configured. Please enter your API key in the sidebar."))
            with st.chat_message("assistant"):
                st.markdown("AI is not configured. Please enter your API key in the sidebar.")

# --- Core Function Handlers ---

def handle_task_generation(gemini_client):
    """
    Handles the "What's next?" command to generate a new task.
    """
    prompt = f"""
    Based on the following project state (tasks and their status), generate the next logical task.
    Project history: {st.session_state.tasks}

    Return a JSON object with two keys:
    - "task_description": A clear and concise description of the new task.
    - "coding_prompt": A detailed, actionable prompt for an executor AI to complete the task.
    """

    ai_response = gemini_client.generate_response(prompt)

    try:
        # Clean the AI response to extract the JSON part
        json_response_str = ai_response.strip().replace('```json', '').replace('```', '')
        task_data = json.loads(json_response_str)

        new_task = {
            "id": len(st.session_state.tasks) + 1,
            "description": task_data['task_description'],
            "prompt": task_data['coding_prompt'],
            "status": "pending",
            "timestamp": time.time()
        }

        st.session_state.tasks.append(new_task)
        log_event("Task Generated", {"task_id": new_task['id'], "description": new_task['description']})
        save_project_data()

        # Display the new task in the chat
        response_text = f"**New Task Generated:** {new_task['description']}\n\n**Prompt for Executor AI:**\n```\n{new_task['prompt']}\n```"
        st.session_state.chat_history.append(("assistant", response_text))
        st.session_state.notification = "New task generated!"
        st.rerun()

    except (json.JSONDecodeError, KeyError) as e:
        # Handle errors in parsing the AI's response
        error_message = f"Failed to parse AI response for task generation: {e}\n\nRaw response:\n{ai_response}"
        st.session_state.chat_history.append(("assistant", error_message))
        with st.chat_message("assistant"):
            st.markdown(error_message)

def handle_task_verification(user_input, gemini_client):
    """
    Handles the 'done' command to verify task completion.
    """
    current_task = next((task for task in st.session_state.tasks if task['status'] == 'pending'), None)

    if not current_task:
        st.session_state.chat_history.append(("assistant", "There are no pending tasks to verify."))
        with st.chat_message("assistant"):
            st.markdown("There are no pending tasks to verify.")
        return

    user_summary = user_input.replace("done", "").strip()
    if not user_summary:
        user_summary = "User marked task as done without providing a summary."

    prompt = f"""
    A task was marked as completed. Verify if the user's summary indicates successful completion.

    Task Description: {current_task['description']}
    Original Coding Prompt: {current_task['prompt']}
    User's Summary of Work: {user_summary}

    Return a JSON object with "verified" (boolean) and "feedback" (string).
    If not verified, provide a follow-up question or suggestion.
    """

    ai_response = gemini_client.generate_response(prompt)

    try:
        json_response_str = ai_response.strip().replace('```json', '').replace('```', '')
        verification_data = json.loads(json_response_str)

        if verification_data.get('verified'):
            current_task['status'] = 'verified'
            log_event("Task Verified", {"task_id": current_task['id'], "summary": user_summary})
            save_project_data()
            st.session_state.notification = f"Task '{current_task['description']}' verified!"
            st.session_state.chat_history.append(("assistant", f"Great job! Task verified: {verification_data['feedback']}"))
            st.rerun()
        else:
            feedback = verification_data.get('feedback', "No specific feedback provided.")
            log_event("Verification Failed", {"task_id": current_task['id'], "summary": user_summary, "feedback": feedback})
            save_project_data()
            response_text = f"**Verification Failed:** {feedback}\nPlease address the feedback and mark the task as 'done' again with more details."
            st.session_state.chat_history.append(("assistant", response_text))
            with st.chat_message("assistant"):
                st.markdown(response_text)

    except (json.JSONDecodeError, KeyError) as e:
        error_message = f"Failed to parse AI verification response: {e}\n\nRaw response:\n{ai_response}"
        st.session_state.chat_history.append(("assistant", error_message))
        with st.chat_message("assistant"):
            st.markdown(error_message)

def log_event(event_type: str, details: dict):
    """Logs an event to the session state for display and persistence."""
    log_entry = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "event": event_type,
        "details": details
    }
    st.session_state.logs.append(log_entry)

def save_project_data():
    """Saves the current tasks and logs to the persistent storage file."""
    storage_data = {
        "tasks": st.session_state.tasks,
        "logs": st.session_state.logs
    }
    save_json(storage_data, 'ai_project_manager/storage.json')

if __name__ == "__main__":
    main()