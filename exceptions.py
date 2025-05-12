class ModBotError(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)


class VoteError(ModBotError): ...
