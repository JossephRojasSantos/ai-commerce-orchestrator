from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer() -> MemorySaver:
    # AsyncRedisSaver requires async context manager setup incompatible with sync build_graph().
    # Use MemorySaver for now; Redis persistence wired via async lifespan in a future task.
    return MemorySaver()
