class ReportGenerator:
    def __init__(self, metadata, reporting_writer):
        self.metadata = metadata
        self.reporting_writer = reporting_writer

    def generate_report(self):
        return self.reporting_writer.write(self.metadata)
