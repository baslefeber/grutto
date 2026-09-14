"""Records what each agent was asked and what it answered.

Used by the review page so you can see and rate each agent separately,
instead of only seeing the coach's final summary.
"""

_transcript = []


def reset():
    _transcript.clear()


def record(agent, question, answer):
    _transcript.append({"agent": agent, "question": question, "answer": answer})


def transcript():
    return list(_transcript)
