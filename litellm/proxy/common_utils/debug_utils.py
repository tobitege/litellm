# Start tracing memory allocations
import os
import tracemalloc

from fastapi import APIRouter

from litellm._logging import verbose_proxy_logger

router = APIRouter()

if os.environ.get("LITELLM_PROFILE", "false").lower() == "true":
    try:
        import objgraph

        print("growth of objects")  # noqa
        objgraph.show_growth()
        print("\n\nMost common types")  # noqa
        objgraph.show_most_common_types()
        roots = objgraph.get_leaking_objects()
        print("\n\nLeaking objects")  # noqa
        objgraph.show_most_common_types(objects=roots)
    except:
        pass

    tracemalloc.start(10)

    @router.get("/memory-usage", include_in_schema=False)
    async def memory_usage():
        # Take a snapshot of the current memory usage
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")
        verbose_proxy_logger.debug("TOP STATS: %s", top_stats)

        # Get the top 50 memory usage lines
        top_50 = top_stats[:50]
        result = []
        for stat in top_50:
            result.append(f"{stat.traceback.format(limit=10)}: {stat.size / 1024} KiB")

        return {"top_50_memory_usage": result}

    @router.get("/memory-usage-in-mem-cache", include_in_schema=False)
    async def memory_usage_in_mem_cache():
        # returns the size of all in-memory caches on the proxy server
        """
        1. user_api_key_cache
        2. router_cache
        3. proxy_logging_cache
        4. internal_usage_cache
        """
        from litellm.proxy.proxy_server import (
            llm_router,
            proxy_logging_obj,
            user_api_key_cache,
        )

        num_items_in_user_api_key_cache = len(
            user_api_key_cache.in_memory_cache.cache_dict
        ) + len(user_api_key_cache.in_memory_cache.ttl_dict)
        num_items_in_llm_router_cache = len(
            llm_router.cache.in_memory_cache.cache_dict
        ) + len(llm_router.cache.in_memory_cache.ttl_dict)
        num_items_in_proxy_logging_obj_cache = len(
            proxy_logging_obj.internal_usage_cache.in_memory_cache.cache_dict
        ) + len(proxy_logging_obj.internal_usage_cache.in_memory_cache.ttl_dict)

        return {
            "num_items_in_user_api_key_cache": num_items_in_user_api_key_cache,
            "num_items_in_llm_router_cache": num_items_in_llm_router_cache,
            "num_items_in_proxy_logging_obj_cache": num_items_in_proxy_logging_obj_cache,
        }


@router.get("/otel-spans", include_in_schema=False)
async def get_otel_spans():
    from litellm.integrations.opentelemetry import OpenTelemetry
    from litellm.proxy.proxy_server import open_telemetry_logger

    open_telemetry_logger: OpenTelemetry = open_telemetry_logger
    otel_exporter = open_telemetry_logger.OTEL_EXPORTER
    recorded_spans = otel_exporter.get_finished_spans()

    print("Spans: ", recorded_spans)  # noqa

    most_recent_parent = None
    most_recent_start_time = 1000000
    spans_grouped_by_parent = {}
    for span in recorded_spans:
        if span.parent is not None:
            parent_trace_id = span.parent.trace_id
            if parent_trace_id not in spans_grouped_by_parent:
                spans_grouped_by_parent[parent_trace_id] = []
            spans_grouped_by_parent[parent_trace_id].append(span.name)

            # check time of span
            if span.start_time > most_recent_start_time:
                most_recent_parent = parent_trace_id
                most_recent_start_time = span.start_time

    # these are otel spans - get the span name
    span_names = [span.name for span in recorded_spans]
    return {
        "otel_spans": span_names,
        "spans_grouped_by_parent": spans_grouped_by_parent,
        "most_recent_parent": most_recent_parent,
    }
