"""Config related utilities."""
import ast
import os
from typing import Any, Callable, Optional


def get_bool_env(env_var_name: str, default: str = "False") -> bool:
    """Convert a 'string boolean' env variable into a true boolean.

    Args:
        env_var_name: Name of target environment variable.
        default: Default if said environment variable isn't defined.

    Returns:
        The env variable as a boolean.

    Raises:
        ValueError: If the env variable isn't a 'string boolean'.
    """
    env_var: str = os.getenv(env_var_name, default)
    try:
        env_var = ast.literal_eval(env_var.title())
        if isinstance(env_var, bool):
            return env_var
        raise ValueError
    except (
        SyntaxError,
        ValueError,
    ):
        raise ValueError(f"Invalid boolean value: {env_var}")


def split_env_values(
    env_var: str,
    sep: str = ",",
    transform_func: Optional[Callable[[str], Any]] = None,
) -> list[Any]:
    """Convert a 'string list' env variable into a true list.

    Args:
        env_var: Value of the environment variable.
        sep: Item separator that the env variable uses.
        transform_func: A function to map the list items.

    Returns:
        The env variable as a Python list.
    """
    if env_var is None:
        return []

    env_var_list = env_var.split(sep)
    if env_var_list == [""]:
        return []

    if transform_func:
        env_var_list = list(map(transform_func, env_var_list))
    return env_var_list
