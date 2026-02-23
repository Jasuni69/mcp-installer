"""
PySpark helper utilities for Microsoft Fabric MCP Server.
This module provides templates, code generation, and execution helpers for PySpark notebooks.
"""

import json
from typing import Dict, List, Any, Optional
from helpers.logging_config import get_logger

logger = get_logger(__name__)

class PySparkTemplateManager:
    """Manages PySpark notebook templates and code generation."""
    
    @staticmethod
    def get_fabric_integration_template() -> Dict[str, Any]:
        """Template for Fabric-specific PySpark operations."""
        return {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# Microsoft Fabric PySpark Integration\n",
                        "\n",
                        "This notebook demonstrates integration with Microsoft Fabric resources using PySpark.\n"
                    ],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Initialize Fabric integration\n",
                        "from pyspark.sql import SparkSession\n",
                        "from pyspark.sql.functions import *\n",
                        "from pyspark.sql.types import *\n",
                        "from delta.tables import DeltaTable\n",
                        "import notebookutils as nbu\n",
                        "\n",
                        "# Spark session is pre-configured in Fabric\n",
                        "print(f\"Spark version: {spark.version}\")\n",
                        "print(f\"Available cores: {spark.sparkContext.defaultParallelism}\")\n",
                        "\n",
                        "# Get current workspace and lakehouse context\n",
                        "print(f\"Current workspace: {nbu.runtime.context.workspaceId}\")\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Connect to Fabric Lakehouse\n",
                        "# List available tables in the default lakehouse\n",
                        "try:\n",
                        "    tables = spark.sql(\"SHOW TABLES\").collect()\n",
                        "    print(\"Available tables in current lakehouse:\")\n",
                        "    for table in tables:\n",
                        "        print(f\"  - {table.database}.{table.tableName}\")\n",
                        "except Exception as e:\n",
                        "    print(f\"No default lakehouse attached or no tables found: {e}\")\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Read from Fabric Lakehouse table\n",
                        "# Replace 'your_table_name' with actual table name\n",
                        "# df = spark.table(\"your_table_name\")\n",
                        "\n",
                        "# Alternative: Read from files in Lakehouse\n",
                        "# df = spark.read.format(\"delta\").load(\"Tables/your_table_name\")\n",
                        "\n",
                        "# For demo, create sample data\n",
                        "sample_data = [\n",
                        "    (1, \"Product A\", 100.0, \"2024-01-01\"),\n",
                        "    (2, \"Product B\", 150.0, \"2024-01-02\"),\n",
                        "    (3, \"Product C\", 200.0, \"2024-01-03\")\n",
                        "]\n",
                        "\n",
                        "schema = StructType([\n",
                        "    StructField(\"id\", IntegerType(), True),\n",
                        "    StructField(\"product_name\", StringType(), True),\n",
                        "    StructField(\"price\", DoubleType(), True),\n",
                        "    StructField(\"date_created\", StringType(), True)\n",
                        "])\n",
                        "\n",
                        "df = spark.createDataFrame(sample_data, schema)\n",
                        "df = df.withColumn(\"date_created\", to_date(col(\"date_created\"), \"yyyy-MM-dd\"))\n",
                        "df.show()\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Write to Fabric Lakehouse as Delta table\n",
                        "table_name = \"fabric_demo_products\"\n",
                        "\n",
                        "# Option 1: Write as managed table\n",
                        "df.write \\\n",
                        "    .format(\"delta\") \\\n",
                        "    .mode(\"overwrite\") \\\n",
                        "    .option(\"overwriteSchema\", \"true\") \\\n",
                        "    .saveAsTable(table_name)\n",
                        "\n",
                        "print(f\"Successfully wrote {df.count()} records to table '{table_name}'\")\n",
                        "\n",
                        "# Verify the table was created\n",
                        "result = spark.table(table_name)\n",
                        "print(\"\\nTable verification:\")\n",
                        "result.show()\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Advanced Delta Lake operations in Fabric\n",
                        "from delta.tables import DeltaTable\n",
                        "\n",
                        "# Create DeltaTable reference\n",
                        "delta_table = DeltaTable.forName(spark, table_name)\n",
                        "\n",
                        "# Show table history\n",
                        "print(\"Table history:\")\n",
                        "delta_table.history().show(truncate=False)\n",
                        "\n",
                        "# Perform merge operation (upsert)\n",
                        "new_data = [\n",
                        "    (1, \"Product A Updated\", 110.0, \"2024-01-01\"),  # Update existing\n",
                        "    (4, \"Product D\", 250.0, \"2024-01-04\")           # Insert new\n",
                        "]\n",
                        "\n",
                        "new_df = spark.createDataFrame(new_data, schema)\n",
                        "new_df = new_df.withColumn(\"date_created\", to_date(col(\"date_created\"), \"yyyy-MM-dd\"))\n",
                        "\n",
                        "# Merge operation\n",
                        "delta_table.alias(\"target\") \\\n",
                        "    .merge(\n",
                        "        new_df.alias(\"source\"),\n",
                        "        \"target.id = source.id\"\n",
                        "    ) \\\n",
                        "    .whenMatchedUpdateAll() \\\n",
                        "    .whenNotMatchedInsertAll() \\\n",
                        "    .execute()\n",
                        "\n",
                        "print(\"\\nAfter merge operation:\")\n",
                        "spark.table(table_name).show()\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                }
            ]
        }
    
    @staticmethod
    def get_streaming_template() -> Dict[str, Any]:
        """Template for PySpark Structured Streaming in Fabric."""
        return {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": [
                        "# PySpark Structured Streaming in Fabric\n",
                        "\n",
                        "This notebook demonstrates real-time data processing using PySpark Structured Streaming.\n"
                    ],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Import streaming libraries\n",
                        "from pyspark.sql import SparkSession\n",
                        "from pyspark.sql.functions import *\n",
                        "from pyspark.sql.types import *\n",
                        "import time\n",
                        "\n",
                        "print(f\"Spark version: {spark.version}\")\n",
                        "print(\"Structured Streaming capabilities enabled\")\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Define schema for streaming data\n",
                        "streaming_schema = StructType([\n",
                        "    StructField(\"timestamp\", TimestampType(), True),\n",
                        "    StructField(\"user_id\", StringType(), True),\n",
                        "    StructField(\"event_type\", StringType(), True),\n",
                        "    StructField(\"value\", DoubleType(), True)\n",
                        "])\n",
                        "\n",
                        "# Create a streaming DataFrame (example with rate source for demo)\n",
                        "streaming_df = spark \\\n",
                        "    .readStream \\\n",
                        "    .format(\"rate\") \\\n",
                        "    .option(\"rowsPerSecond\", 10) \\\n",
                        "    .load()\n",
                        "\n",
                        "# Transform the rate stream to simulate real events\n",
                        "events_df = streaming_df \\\n",
                        "    .withColumn(\"user_id\", concat(lit(\"user_\"), (col(\"value\") % 100).cast(\"string\"))) \\\n",
                        "    .withColumn(\"event_type\", \n",
                        "        when(col(\"value\") % 3 == 0, \"purchase\")\n",
                        "        .when(col(\"value\") % 3 == 1, \"view\")\n",
                        "        .otherwise(\"click\")\n",
                        "    ) \\\n",
                        "    .withColumn(\"event_value\", (col(\"value\") % 1000).cast(\"double\")) \\\n",
                        "    .select(\"timestamp\", \"user_id\", \"event_type\", \"event_value\")\n",
                        "\n",
                        "print(\"Streaming DataFrame created\")\n",
                        "print(f\"Schema: {events_df.schema}\")\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Streaming aggregations\n",
                        "# Count events by type in 30-second windows\n",
                        "windowed_counts = events_df \\\n",
                        "    .withWatermark(\"timestamp\", \"30 seconds\") \\\n",
                        "    .groupBy(\n",
                        "        window(col(\"timestamp\"), \"30 seconds\"),\n",
                        "        col(\"event_type\")\n",
                        "    ) \\\n",
                        "    .count() \\\n",
                        "    .orderBy(\"window\")\n",
                        "\n",
                        "# Start streaming query (console output)\n",
                        "query = windowed_counts \\\n",
                        "    .writeStream \\\n",
                        "    .outputMode(\"complete\") \\\n",
                        "    .format(\"console\") \\\n",
                        "    .option(\"truncate\", False) \\\n",
                        "    .trigger(processingTime=\"10 seconds\") \\\n",
                        "    .start()\n",
                        "\n",
                        "print(\"Streaming query started. Check output below...\")\n",
                        "print(f\"Query ID: {query.id}\")\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Let the stream run for a short time\n",
                        "import time\n",
                        "time.sleep(30)  # Run for 30 seconds\n",
                        "\n",
                        "# Stop the query\n",
                        "query.stop()\n",
                        "print(\"Streaming query stopped\")\n",
                        "\n",
                        "# Show query progress\n",
                        "print(\"\\nQuery progress:\")\n",
                        "print(query.lastProgress)\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                },
                {
                    "cell_type": "code",
                    "source": [
                        "# Stream to Delta Lake table\n",
                        "streaming_table = \"streaming_events\"\n",
                        "\n",
                        "# Create another streaming query that writes to Delta\n",
                        "delta_query = events_df \\\n",
                        "    .writeStream \\\n",
                        "    .format(\"delta\") \\\n",
                        "    .outputMode(\"append\") \\\n",
                        "    .option(\"checkpointLocation\", \"/tmp/checkpoint/streaming_events\") \\\n",
                        "    .table(streaming_table)\n",
                        "\n",
                        "print(f\"Started streaming to Delta table: {streaming_table}\")\n",
                        "print(f\"Query ID: {delta_query.id}\")\n",
                        "\n",
                        "# Let it run briefly\n",
                        "time.sleep(20)\n",
                        "\n",
                        "# Stop and check results\n",
                        "delta_query.stop()\n",
                        "\n",
                        "# Read from the Delta table\n",
                        "result_df = spark.table(streaming_table)\n",
                        "print(f\"\\nTotal records in Delta table: {result_df.count()}\")\n",
                        "result_df.show(20)\n"
                    ],
                    "execution_count": None,
                    "outputs": [],
                    "metadata": {}
                }
            ]
        }

class PySparkCodeGenerator:
    """Generates PySpark code snippets for common operations."""
    
    @staticmethod
    def generate_fabric_lakehouse_reader(lakehouse_name: str, table_name: str) -> str:
        """Generate code to read from a Fabric Lakehouse table."""
        return f"""# Read from Fabric Lakehouse table
df = spark.table("{lakehouse_name}.{table_name}")

# Alternative: Read from Delta files directly
# df = spark.read.format("delta").load("Tables/{table_name}")

# Show basic info
print(f"Records: {{df.count()}}")
print(f"Columns: {{len(df.columns)}}")
df.printSchema()
df.show(10)"""

    @staticmethod
    def generate_fabric_lakehouse_writer(table_name: str, mode: str = "overwrite") -> str:
        """Generate code to write to a Fabric Lakehouse table."""
        return f"""# Write to Fabric Lakehouse table
df.write \\
    .format("delta") \\
    .mode("{mode}") \\
    .option("overwriteSchema", "true") \\
    .saveAsTable("{table_name}")

print(f"Successfully wrote {{df.count()}} records to table '{table_name}'")

# Verify the write
verification_df = spark.table("{table_name}")
print(f"Verification - Table now has {{verification_df.count()}} records")"""

    @staticmethod
    def generate_delta_merge_operation(target_table: str, source_df_name: str, join_condition: str) -> str:
        """Generate code for Delta Lake merge operations."""
        return f"""# Delta Lake merge operation (UPSERT)
from delta.tables import DeltaTable

# Create DeltaTable reference
target_table = DeltaTable.forName(spark, "{target_table}")

# Perform merge operation
target_table.alias("target") \\
    .merge(
        {source_df_name}.alias("source"),
        "{join_condition}"
    ) \\
    .whenMatchedUpdateAll() \\
    .whenNotMatchedInsertAll() \\
    .execute()

print("Merge operation completed successfully")
print(f"Table now has {{spark.table('{target_table}').count()}} records")"""

    @staticmethod
    def generate_performance_monitoring() -> str:
        """Generate code for monitoring PySpark performance."""
        return """# PySpark Performance Monitoring

# 1. Check Spark configuration
print("=== Spark Configuration ===")
for key, value in spark.sparkContext.getConf().getAll():
    if 'spark.sql' in key or 'spark.serializer' in key:
        print(f"{key}: {value}")

# 2. Monitor DataFrame operations
from pyspark.sql.utils import AnalysisException
import time

def monitor_operation(df, operation_name):
    start_time = time.time()
    try:
        count = df.count()
        end_time = time.time()
        duration = end_time - start_time
        print(f"{operation_name}: {count} records in {duration:.2f} seconds")
        return count, duration
    except Exception as e:
        print(f"Error in {operation_name}: {e}")
        return 0, 0

# Example usage:
# count, duration = monitor_operation(df, "DataFrame Count")

# 3. Show execution plan
print("\\n=== Execution Plan ===")
df.explain(True)

# 4. Cache analysis
print("\\n=== Storage Levels ===")
print(f"DataFrame cached: {df.is_cached}")
if df.is_cached:
    print(f"Storage level: {df.storageLevel}")"""

class PySparkValidator:
    """Validates PySpark code and suggests optimizations."""
    
    @staticmethod
    def validate_fabric_compatibility(code: str) -> Dict[str, List[str]]:
        """Check if code is compatible with Microsoft Fabric."""
        issues = []
        suggestions = []
        
        # Check for Fabric-specific patterns
        if 'SparkSession.builder' in code:
            issues.append("❌ Don't create SparkSession in Fabric - use pre-configured 'spark' variable")
        
        if 'notebookutils' not in code and any(pattern in code for pattern in ['lakehouse', 'workspace']):
            suggestions.append("💡 Consider using 'notebookutils' for Fabric integration")
        
        if '.saveAsTable(' in code and 'format("delta")' not in code:
            suggestions.append("💡 Specify Delta format explicitly when saving tables in Fabric")
        
        if 'jdbc' in code.lower():
            suggestions.append("💡 Consider using Fabric's built-in connectors instead of JDBC")
        
        return {
            "issues": issues,
            "suggestions": suggestions
        }
    
    @staticmethod
    def check_performance_patterns(code: str) -> Dict[str, List[str]]:
        """Check for performance anti-patterns and optimizations."""
        warnings = []
        optimizations = []
        
        # Performance anti-patterns
        if '.collect()' in code:
            warnings.append("⚠️ .collect() can cause OOM on large datasets")
        
        if 'rdd.' in code and 'parallelize' not in code:
            warnings.append("⚠️ RDD operations are less optimized than DataFrame operations")
        
        if code.count('spark.read') > 3 and '.cache()' not in code:
            optimizations.append("💡 Consider caching frequently accessed DataFrames")
        
        if '.join(' in code and 'broadcast' not in code:
            optimizations.append("💡 Consider broadcast joins for small dimension tables")
        
        if '.write.' in code and 'partitionBy' not in code:
            optimizations.append("💡 Consider partitioning large datasets for better performance")
        
        return {
            "warnings": warnings,
            "optimizations": optimizations
        }

def create_notebook_from_template(template_name: str, custom_params: Optional[Dict] = None) -> Dict[str, Any]:
    """Create a complete notebook from a template."""
    template_manager = PySparkTemplateManager()
    
    templates = {
        "fabric_integration": template_manager.get_fabric_integration_template(),
        "streaming": template_manager.get_streaming_template(),
    }
    
    if template_name not in templates:
        raise ValueError(f"Unknown template: {template_name}. Available: {list(templates.keys())}")
    
    template = templates[template_name]
    
    # Create notebook structure
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": template["cells"],
        "metadata": {
            "language_info": {"name": "python"},
            "kernel_info": {"name": "synapse_pyspark"},
            "description": f"PySpark notebook created from {template_name} template"
        }
    }
    
    return notebook
