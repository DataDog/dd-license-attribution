class ReportGenerator:
    def __init__(self, reporting_writer):
        self.reporting_writer = reporting_writer

    def generate_report(self, metadata):
        return self.reporting_writer.write(metadata)
