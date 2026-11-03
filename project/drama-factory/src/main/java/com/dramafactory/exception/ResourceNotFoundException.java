package com.dramafactory.exception;

public class ResourceNotFoundException extends RuntimeException {

    private final String resource;
    private final Long id;
    private final String key;

    public ResourceNotFoundException(String resource, Long id) {
        super(resource + " not found: " + id);
        this.resource = resource;
        this.id = id;
        this.key = null;
    }

    private ResourceNotFoundException(String resource, Long id, String key) {
        super(resource + " not found: " + (key != null ? key : id));
        this.resource = resource;
        this.id = id;
        this.key = key;
    }

    /**
     * 按字符串键（如预设名、手册名）构造未找到异常。
     *
     * @param resource 资源类型名
     * @param key      字符串键
     * @return 异常实例
     */
    public static ResourceNotFoundException withKey(String resource, String key) {
        return new ResourceNotFoundException(resource, null, key);
    }

    public String getResource() {
        return resource;
    }

    public Long getId() {
        return id;
    }

    public String getKey() {
        return key;
    }
}
