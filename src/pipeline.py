class Pipeline:
  def __init__(self, pipeline, opts):
    self.pipeline = pipeline
    self.opts = opts

  def run(self, input_init):
    input = input_init._asdict() | self.opts
    for title, func, opts in self.pipeline:
      input = func(input | opts)


