#include "irx_exception_runtime.h"
#include "irx_class_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define IRX_EXCEPTION_MAX_CHAIN 32
#define IRX_EXCEPTION_MAX_FRAMES 64

typedef struct {
  char* source;
  int32_t line;
  int32_t col;
} irx_exception_frame;

struct irx_exception_info {
  uint64_t references;
  char* name;
  char* message;
  char** ancestry;
  int32_t ancestry_count;
  char* source;
  char* code;
  int32_t line;
  int32_t col;
  int32_t suppress_context;
  int32_t depth;
  irx_exception_info* cause;
  irx_exception_info* context;
  irx_exception_info* cleanup;
  irx_exception_frame frames[IRX_EXCEPTION_MAX_FRAMES];
  int32_t frame_count;
};

struct irx_exception_value {
  void* payload;
  irx_exception_info* info;
  irx_exception_info** object_slot;
};

struct irx_exception_scope {
  irx_exception_scope* previous_scope;
  irx_exception_value* previous_handled;
  irx_exception_value* saved;
  int32_t kind;
};

struct irx_exception_context {
  irx_exception_value* pending;
  irx_exception_value* handled;
  irx_exception_scope* scopes;
  int32_t discarding;
};

static void irx_exception_fatal(const char* message) {
  fputs("ARX_RUNTIME_FAIL|ARX-RUNTIME-EXCEPTION-FATAL|"
        "<unknown>|-1|-1|", stderr);
  fputs(message, stderr);
  fputc('\n', stderr);
  fflush(stderr);
  exit(EXIT_FAILURE);
}

static char* irx_exception_copy_text(const char* text) {
  char* copy;
  size_t size;
  if (!text) text = "";
  size = strlen(text);
  if (size == SIZE_MAX) return NULL;
  copy = malloc(size + 1);
  if (copy) memcpy(copy, text, size + 1);
  return copy;
}

void irx_exception_info_retain(irx_exception_info* info) {
  if (!info) return;
  if (!info->references || info->references == UINT64_MAX)
    irx_exception_fatal("invalid exception record retain");
  info->references++;
}

void irx_exception_info_release(irx_exception_info* info) {
  int32_t index;
  if (!info) return;
  if (!info->references)
    irx_exception_fatal("invalid exception record release");
  if (--info->references) return;
  free(info->name);
  free(info->message);
  free(info->source);
  free(info->code);
  for (index = 0; index < info->ancestry_count; index++)
    free(info->ancestry[index]);
  free(info->ancestry);
  for (index = 0; index < info->frame_count; index++)
    free(info->frames[index].source);
  irx_exception_info_release(info->cause);
  irx_exception_info_release(info->context);
  irx_exception_info_release(info->cleanup);
  free(info);
}

int32_t irx_exception_info_create(const char* name, const char* message,
    const char* const* ancestry, int32_t count, irx_exception_info** out) {
  irx_exception_info* info;
  int32_t index;
  if (out) *out = NULL;
  if (!out || !name || !message || !ancestry || count <= 0) return -1;
  for (index = 0; index < count; index++)
    if (!ancestry[index] || !ancestry[index][0]) return -1;
  info = calloc(1, sizeof(*info));
  if (!info) return -1;
  info->references = 1;
  info->line = info->col = -1;
  info->name = irx_exception_copy_text(name);
  info->message = irx_exception_copy_text(message);
  info->ancestry = calloc((size_t)count, sizeof(char*));
  if (!info->name || !info->message || !info->ancestry) goto failed;
  for (index = 0; index < count; index++) {
    info->ancestry[index] = irx_exception_copy_text(ancestry[index]);
    if (!info->ancestry[index]) goto failed;
    info->ancestry_count++;
  }
  *out = info;
  return 0;
failed:
  irx_exception_info_release(info);
  return -1;
}

const char* irx_exception_info_message(const irx_exception_info* info) {
  return info ? info->message : "";
}

static irx_exception_info* irx_exception_info_copy(
    const irx_exception_info* original) {
  irx_exception_info* copy = NULL;
  int32_t index;
  if (!original || irx_exception_info_create(original->name,
      original->message, (const char* const*)original->ancestry,
      original->ancestry_count, &copy)) return NULL;
  if (original->source) {
    copy->source = irx_exception_copy_text(original->source);
    if (!copy->source) goto failed;
  }
  if (original->code) {
    copy->code = irx_exception_copy_text(original->code);
    if (!copy->code) goto failed;
  }
  copy->line = original->line;
  copy->col = original->col;
  copy->suppress_context = original->suppress_context;
  copy->depth = original->depth;
  for (index = 0; index < original->frame_count; index++) {
    copy->frames[index] = original->frames[index];
    copy->frames[index].source =
        irx_exception_copy_text(original->frames[index].source);
    if (!copy->frames[index].source) goto failed;
    copy->frame_count++;
  }
  copy->cause = original->cause;
  copy->context = original->context;
  copy->cleanup = original->cleanup;
  irx_exception_info_retain(copy->cause);
  irx_exception_info_retain(copy->context);
  irx_exception_info_retain(copy->cleanup);
  return copy;
failed:
  irx_exception_info_release(copy);
  return NULL;
}

static void irx_exception_link(irx_exception_info* info,
    irx_exception_info** slot, irx_exception_info* previous) {
  irx_exception_info_release(*slot);
  *slot = NULL;
  if (!previous || previous->depth >= IRX_EXCEPTION_MAX_CHAIN - 1) return;
  irx_exception_info_retain(previous);
  *slot = previous;
  if (info->depth <= previous->depth) info->depth = previous->depth + 1;
}

static void irx_exception_replace_info(irx_exception_value* value,
                                      irx_exception_info* info) {
  irx_exception_info* previous = value->info;
  value->info = info;
  if (value->object_slot) {
    irx_exception_info_retain(info);
    irx_exception_info_release(*value->object_slot);
    *value->object_slot = info;
  }
  irx_exception_info_release(previous);
}

int32_t irx_exception_context_create(irx_exception_context** out) {
  if (!out) return -1;
  *out = calloc(1, sizeof(**out));
  return *out ? 0 : -1;
}

int32_t irx_exception_raise(irx_exception_context* context, void* payload,
    irx_exception_info** slot, irx_exception_info* cause, int32_t mode,
    const char* source, int32_t line, int32_t col, const char* code) {
  irx_exception_info* info;
  irx_exception_value* value;
  char error[IRX_CLASS_ERROR_CAPACITY];
  if (!context || context->pending || !payload || !slot || !*slot ||
      mode < 0 || mode > 2 || (mode == 1 && !cause)) return -1;
  info = irx_exception_info_copy(*slot);
  if (!info) return -1;
  free(info->source);
  free(info->code);
  info->source = irx_exception_copy_text(source ? source : "<unknown>");
  info->code = irx_exception_copy_text(
      code && code[0] ? code : "ARX-RUNTIME-EXCEPTION-001");
  if (!info->source || !info->code) goto failed;
  info->line = line > 0 ? line : -1;
  info->col = line > 0 && col > 0 ? col : -1;
  info->suppress_context = mode != 0;
  irx_exception_link(info, &info->context,
                    context->handled ? context->handled->info : NULL);
  irx_exception_link(info, &info->cause, mode == 1 ? cause : NULL);
  value = malloc(sizeof(*value));
  if (!value) goto failed;
  if (irx_class_retain(payload, error)) {
    free(value);
    goto failed;
  }
  value->payload = payload;
  value->info = info;
  value->object_slot = slot;
  irx_exception_info_retain(info);
  irx_exception_info_release(*slot);
  *slot = info;
  context->pending = value;
  return 1;
failed:
  irx_exception_info_release(info);
  return -1;
}

int32_t irx_exception_reraise(irx_exception_context* context) {
  irx_exception_value* copy;
  char error[IRX_CLASS_ERROR_CAPACITY];
  if (!context || context->pending || !context->handled) return -1;
  copy = malloc(sizeof(*copy));
  if (!copy) irx_exception_fatal("out of memory re-raising exception");
  *copy = *context->handled;
  if (irx_class_retain(copy->payload, error)) {
    free(copy);
    irx_exception_fatal("cannot retain active exception");
  }
  irx_exception_info_retain(copy->info);
  context->pending = copy;
  return 1;
}

int32_t irx_exception_pending(const irx_exception_context* context) {
  return context && context->pending ? 1 : 0;
}

int32_t irx_exception_matches(const irx_exception_context* context,
                             const char* identity) {
  int32_t index;
  irx_exception_info* info;
  if (!context || !context->pending || !identity) return 0;
  info = context->pending->info;
  for (index = 0; index < info->ancestry_count; index++)
    if (!strcmp(info->ancestry[index], identity)) return 1;
  return 0;
}

void* irx_exception_handled_payload(const irx_exception_context* context) {
  return context && context->handled ? context->handled->payload : NULL;
}

irx_exception_info* irx_exception_pending_info(
    const irx_exception_context* context) {
  return context && context->pending ? context->pending->info : NULL;
}

static void irx_exception_record_secondary(irx_exception_value* original,
                                         irx_exception_info* secondary) {
  irx_exception_info* copy = irx_exception_info_copy(original->info);
  if (!copy) return; /* Reporting exhaustion must not replace the failure. */
  if (copy->cleanup) {
    irx_exception_info* next = irx_exception_info_copy(secondary);
    if (next) {
      irx_exception_link(next, &next->cleanup, copy->cleanup);
      irx_exception_link(copy, &copy->cleanup, next);
      irx_exception_info_release(next);
    }
  } else {
    irx_exception_link(copy, &copy->cleanup, secondary);
  }
  irx_exception_replace_info(original, copy);
}

void irx_exception_pending_discard(irx_exception_context* context,
                                  irx_exception_value* value) {
  irx_exception_value* saved;
  irx_exception_value* secondary;
  char error[IRX_CLASS_ERROR_CAPACITY];
  int32_t status;
  if (!value) return;
  if (!context || ++context->discarding > IRX_EXCEPTION_MAX_CHAIN)
    irx_exception_fatal("exception destruction repeatedly failed");
  saved = context->pending;
  context->pending = NULL;
  status = irx_class_release(context, value->payload, error);
  irx_exception_info_release(value->info);
  free(value);
  secondary = context->pending;
  context->pending = saved;
  if (secondary) {
    if (saved) {
      irx_exception_record_secondary(saved, secondary->info);
      irx_exception_pending_discard(context, secondary);
    } else {
      context->pending = secondary;
    }
  } else if (status) {
    irx_exception_fatal("exception destructor failed without a pending value");
  }
  context->discarding--;
}

irx_exception_value* irx_exception_pending_take(irx_exception_context* context) {
  irx_exception_value* value;
  if (!context) irx_exception_fatal("missing exception context");
  value = context->pending;
  context->pending = NULL;
  return value;
}

void irx_exception_pending_restore(irx_exception_context* context,
                                  irx_exception_value* value) {
  if (!context || context->pending)
    irx_exception_fatal("restoring into an occupied exception slot");
  context->pending = value;
}

static irx_exception_scope* irx_exception_scope_enter(
    irx_exception_context* context, int32_t kind) {
  irx_exception_scope* scope;
  if (!context || (kind == 1 && !context->pending))
    irx_exception_fatal("invalid exception scope entry");
  scope = malloc(sizeof(*scope));
  if (!scope) irx_exception_fatal("out of memory entering exception scope");
  scope->kind = kind;
  scope->saved = irx_exception_pending_take(context);
  scope->previous_handled = context->handled;
  scope->previous_scope = context->scopes;
  context->scopes = scope;
  if (scope->saved) context->handled = scope->saved;
  return scope;
}

static void irx_exception_scope_pop(irx_exception_context* context,
                                   irx_exception_scope* scope, int32_t kind) {
  if (!context || !scope || context->scopes != scope || scope->kind != kind)
    irx_exception_fatal("exception scopes must leave in reverse order");
  context->scopes = scope->previous_scope;
  context->handled = scope->previous_handled;
}

irx_exception_scope* irx_exception_handler_enter(irx_exception_context* context) {
  return irx_exception_scope_enter(context, 1);
}

void irx_exception_handler_leave(irx_exception_context* context,
                                irx_exception_scope* scope) {
  irx_exception_scope_pop(context, scope, 1);
  irx_exception_pending_discard(context, scope->saved);
  free(scope);
}

irx_exception_scope* irx_exception_finally_enter(irx_exception_context* context) {
  return irx_exception_scope_enter(context, 2);
}

void irx_exception_finally_leave(irx_exception_context* context,
                                irx_exception_scope* scope, int32_t preserve) {
  irx_exception_scope_pop(context, scope, 2);
  if (preserve && !context->pending)
    context->pending = scope->saved;
  else
    irx_exception_pending_discard(context, scope->saved);
  free(scope);
}

irx_exception_scope* irx_exception_cleanup_enter(irx_exception_context* context) {
  return irx_exception_scope_enter(context, 3);
}

void irx_exception_cleanup_leave(irx_exception_context* context,
                                irx_exception_scope* scope) {
  irx_exception_value* secondary;
  irx_exception_scope_pop(context, scope, 3);
  if (scope->saved) {
    secondary = context->pending;
    context->pending = scope->saved;
    if (secondary) {
      irx_exception_record_secondary(scope->saved, secondary->info);
      irx_exception_pending_discard(context, secondary);
    }
  }
  free(scope);
}

void irx_exception_context_destroy(irx_exception_context* context) {
  int count = 0;
  if (!context) return;
  if (context->scopes || context->handled)
    irx_exception_fatal("destroying an active exception context");
  while (context->pending) {
    if (++count > IRX_EXCEPTION_MAX_CHAIN)
      irx_exception_fatal("exception destruction repeatedly failed");
    irx_exception_pending_discard(context, irx_exception_pending_take(context));
  }
  free(context);
}

void irx_exception_trace(irx_exception_context* context, const char* source,
                         int32_t line, int32_t col) {
  irx_exception_info* copy;
  irx_exception_frame* frame;
  if (!context || !context->pending || !source || line <= 0 || col <= 0 ||
      context->pending->info->frame_count >= IRX_EXCEPTION_MAX_FRAMES) return;
  copy = irx_exception_info_copy(context->pending->info);
  if (!copy) return;
  frame = &copy->frames[copy->frame_count];
  frame->source = irx_exception_copy_text(source);
  if (!frame->source) {
    irx_exception_info_release(copy);
    return;
  }
  frame->line = line;
  frame->col = col;
  copy->frame_count++;
  irx_exception_replace_info(context->pending, copy);
}

static void irx_exception_write_field(const char* text) {
  const unsigned char* cursor = (const unsigned char*)(text ? text : "");
  while (*cursor) {
    switch (*cursor) {
      case '\\': fputs("\\\\", stderr); break;
      case '\n': fputs("\\n", stderr); break;
      case '\r': fputs("\\r", stderr); break;
      case '\t': fputs("\\t", stderr); break;
      case '|': fputs("\\p", stderr); break;
      default: fputc(*cursor, stderr); break;
    }
    cursor++;
  }
}

static void irx_exception_report_info(const irx_exception_info* info,
                                    const char* role, int32_t depth, int32_t* budget) {
  int32_t index;
  if (!info || depth > IRX_EXCEPTION_MAX_CHAIN || !*budget) return;
  (*budget)--;
  if (info->cause)
    irx_exception_report_info(info->cause, "cause", depth + 1, budget);
  else if (!info->suppress_context)
    irx_exception_report_info(info->context, "context", depth + 1, budget);
  irx_exception_report_info(info->cleanup, "cleanup", depth + 1, budget);
  fprintf(stderr, "ARX_EXCEPTION|%s|", role);
  irx_exception_write_field(info->code ? info->code : "ARX-RUNTIME-EXCEPTION-001");
  fputc('|', stderr);
  irx_exception_write_field(info->name);
  fputc('|', stderr);
  irx_exception_write_field(info->source ? info->source : "<unknown>");
  fprintf(stderr, "|%d|%d|", info->line, info->col);
  irx_exception_write_field(info->message);
  fputc('\n', stderr);
  for (index = 0; index < info->frame_count; index++) {
    fputs("ARX_EXCEPTION_FRAME|", stderr);
    irx_exception_write_field(info->frames[index].source);
    fprintf(stderr, "|%d|%d\n", info->frames[index].line,
            info->frames[index].col);
  }
}

void irx_exception_report(const irx_exception_context* context) {
  if (context && context->pending) {
    int32_t budget = IRX_EXCEPTION_MAX_CHAIN;
    irx_exception_report_info(context->pending->info, "root", 0, &budget);
    fflush(stderr);
  }
}
