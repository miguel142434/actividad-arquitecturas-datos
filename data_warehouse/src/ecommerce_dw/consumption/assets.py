"""Definiciones QuickSight sobre los marts originales; no contienen credenciales."""
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / 'quicksight'
DATASET_ID = 'de-dw-aws-sales'
DATA_SOURCE_ID = 'de-dw-aws-redshift'
DASHBOARD_ID = 'de-dw-aws-sales'
ANALYSIS_ID = 'de-dw-aws-sales'
SQL = (SQL_DIR/'sales.sql').read_text().strip()
VALIDATION_SQL = (SQL_DIR/'validate_sales.sql').read_text()


def column(name):
    return {'DataSetIdentifier': 'ventas', 'ColumnName': name}


def measure(field_id):
    return {'NumericalMeasureField': {
        'FieldId': field_id, 'Column': column('subtotal'),
        'AggregationFunction': {'SimpleNumericalAggregation': 'SUM'},
        # El servicio no admite COP en CurrencyDisplayFormatConfiguration.
        # Mostrar la unidad explícita, sin convertir ni redondear a miles.
        'FormatConfiguration': {'FormatConfiguration': {'NumberDisplayFormatConfiguration': {
            'Suffix': ' COP', 'NumberScale': 'NONE',
            'DecimalPlacesConfiguration': {'DecimalPlaces': 2}}}}}}


def definition(dataset_arn):
    return {
        'DataSetIdentifierDeclarations': [{'Identifier': 'ventas', 'DataSetArn': dataset_arn}],
        'Sheets': [{
            'SheetId': 'ventas', 'Name': 'Ventas de comercio electrónico',
            'ContentType': 'INTERACTIVE',
            'FilterControls': [{'Dropdown': {
                'FilterControlId': 'categoria-control', 'SourceFilterId': 'categoria-filter',
                'Title': 'Categoría', 'Type': 'MULTI_SELECT'}}],
            'Visuals': [
                {'KPIVisual': {'VisualId': 'ventas-total',
                    'Title': {'Visibility': 'VISIBLE', 'FormatText': {'PlainText': 'Ventas totales (COP)'}},
                    'ChartConfiguration': {'FieldWells': {'Values': [measure('ventas-total-suma')]}}}},
                {'BarChartVisual': {'VisualId': 'ventas-fecha',
                    'Title': {'Visibility': 'VISIBLE', 'FormatText': {'PlainText': 'Ventas por mes (COP)'}},
                    'ChartConfiguration': {
                        'FieldWells': {'BarChartAggregatedFieldWells': {
                            'Category': [{'DateDimensionField': {
                                'FieldId': 'fecha-mes', 'Column': column('fecha'), 'DateGranularity': 'MONTH'}}],
                            'Values': [measure('ventas-fecha-suma')]}},
                        'SortConfiguration': {'CategorySort': [{'FieldSort': {
                            'FieldId': 'fecha-mes', 'Direction': 'ASC'}}]},
                        'Orientation': 'VERTICAL'}}}],
            'Layouts': [{'Configuration': {'GridLayout': {'Elements': [
                {'ElementId': 'categoria-control', 'ElementType': 'FILTER_CONTROL',
                 'ColumnIndex': 0, 'ColumnSpan': 18, 'RowIndex': 0, 'RowSpan': 4},
                {'ElementId': 'ventas-total', 'ElementType': 'VISUAL',
                 'ColumnIndex': 0, 'ColumnSpan': 36, 'RowIndex': 4, 'RowSpan': 5},
                {'ElementId': 'ventas-fecha', 'ElementType': 'VISUAL',
                 'ColumnIndex': 0, 'ColumnSpan': 36, 'RowIndex': 9, 'RowSpan': 14}],
                'CanvasSizeOptions': {'ScreenCanvasSizeOptions': {'ResizeOption': 'RESPONSIVE'}}}}}]}],
        'FilterGroups': [{
            'FilterGroupId': 'categoria-group', 'Status': 'ENABLED', 'CrossDataset': 'SINGLE_DATASET',
            'Filters': [{'CategoryFilter': {
                'FilterId': 'categoria-filter', 'Column': column('categoria'),
                'Configuration': {'FilterListConfiguration': {
                    'MatchOperator': 'CONTAINS', 'SelectAllOptions': 'FILTER_ALL_VALUES',
                    'NullOption': 'NON_NULLS_ONLY'}}}}],
            'ScopeConfiguration': {'SelectedSheets': {'SheetVisualScopingConfigurations': [
                {'SheetId': 'ventas', 'Scope': 'ALL_VISUALS'}]}}}]}


def requests(account, principal, host, vpc_arn):
    prefix = f'arn:aws:quicksight:us-east-1:{account}'
    source_arn = f'{prefix}:datasource/{DATA_SOURCE_ID}'
    dataset_arn = f'{prefix}:dataset/{DATASET_ID}'
    def permissions(actions):
        return [{'Principal': principal, 'Actions': ['quicksight:'+action for action in actions]}]
    tags = [{'Key': 'Project', 'Value': 'DE-DW-AWS'}]
    source = {'AwsAccountId': account, 'DataSourceId': DATA_SOURCE_ID, 'Name': 'DE-DW-AWS Redshift privado',
        'Type': 'REDSHIFT', 'DataSourceParameters': {'RedshiftParameters': {
            'Host': host, 'Port': 5439, 'Database': 'ecommerce'}},
        'VpcConnectionProperties': {'VpcConnectionArn': vpc_arn},
        'SslProperties': {'DisableSsl': False}, 'Tags': tags,
        'Permissions': permissions(['DescribeDataSource','DescribeDataSourcePermissions','PassDataSource',
                                    'UpdateDataSource','DeleteDataSource','UpdateDataSourcePermissions'])}
    columns = [{'Name': name, 'Type': kind} for name, kind in (
        ('sale_sk','STRING'),('fecha','DATETIME'),('categoria','STRING'),
        ('canal','STRING'),('cantidad','INTEGER'),('subtotal','DECIMAL'))]
    columns[-1]['SubType'] = 'FIXED'
    dataset = {'AwsAccountId': account, 'DataSetId': DATASET_ID, 'Name': 'DE-DW-AWS Ventas',
        'ImportMode': 'SPICE', 'PhysicalTableMap': {'ventas': {'CustomSql': {
            'DataSourceArn': source_arn, 'Name': 'ventas', 'SqlQuery': SQL, 'Columns': columns}}},
        'Tags': tags, 'Permissions': permissions(['DescribeDataSet','DescribeDataSetPermissions','PassDataSet',
            'DescribeIngestion','ListIngestions','UpdateDataSet','DeleteDataSet','CreateIngestion',
            'CancelIngestion','UpdateDataSetPermissions'])}
    base = {'AwsAccountId': account, 'Name': 'DE-DW-AWS · Ventas',
            'Definition': definition(dataset_arn), 'Tags': tags}
    analysis = {**base, 'AnalysisId': ANALYSIS_ID, 'Permissions': permissions([
        'RestoreAnalysis','UpdateAnalysisPermissions','DeleteAnalysis','DescribeAnalysisPermissions',
        'QueryAnalysis','DescribeAnalysis','UpdateAnalysis'])}
    dashboard = {**base, 'DashboardId': DASHBOARD_ID, 'Permissions': permissions([
        'DescribeDashboard','ListDashboardVersions','UpdateDashboardPermissions','QueryDashboard',
        'UpdateDashboard','DeleteDashboard','DescribeDashboardPermissions','UpdateDashboardPublishedVersion'])}
    return {'source': source, 'dataset': dataset, 'analysis': analysis, 'dashboard': dashboard}
