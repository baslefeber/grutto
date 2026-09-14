"""The safety gate, enforced in code.

The safety officer's veto used to live in a system prompt: the agent was asked
to say REJECTED, and the coach was asked to respect it. A prompt is a request,
not a guarantee. Nothing stopped a rejected week reaching the watch.

Now the verdict is a typed object, the gate records what was actually approved,
and the publisher refuses anything that does not match. No wording in any
prompt can get a rejected week past this.
"""

import hashlib

from pydantic import BaseModel, Field


class Verdict(BaseModel):
    """What the safety officer returns. Not free text."""

    approved: bool = Field(description="True only if this week is safe to run as written.")
    reason: str = Field(description="Why, in one or two plain sentences, with the numbers.")
    proposed_week_km: float = Field(description="Total kilometres in the week being judged.")
    safe_ceiling_km: float = Field(description="The most this runner should do this week.")


class Gate:
    """Remembers what was approved. Nothing else gets published."""

    def __init__(self):
        self.approved_fingerprint = None
        self.attempts = 0
        self.rejections = []
        self.last_verdict = None

    @staticmethod
    def _fingerprint(plan_text):
        return hashlib.sha256(" ".join(plan_text.split()).lower().encode()).hexdigest()[:16]

    def record(self, plan_text, verdict: Verdict):
        self.attempts += 1
        self.last_verdict = verdict
        if verdict.approved:
            self.approved_fingerprint = self._fingerprint(plan_text)
        else:
            self.rejections.append(verdict.reason)
        return verdict

    def allows(self, plan_text):
        return (self.approved_fingerprint is not None
                and self._fingerprint(plan_text) == self.approved_fingerprint)

    def reset(self):
        self.__init__()

    def summary(self):
        return {
            "approved": self.approved_fingerprint is not None,
            "attempts": self.attempts,
            "rejections": list(self.rejections),
            "ceiling_km": self.last_verdict.safe_ceiling_km if self.last_verdict else None,
        }


_gate = Gate()


def gate():
    return _gate
