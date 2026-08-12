from dataclasses import dataclass
from typing import Callable

@dataclass
class Tool:
    schema:dict
    function:Callable