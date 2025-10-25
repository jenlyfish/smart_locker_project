/**
 * Smart Locker System - Items Management Page
 *
 * @author Alp
 * @date 2024-12-XX
 * @description Items management interface for administrators
 */

import React, { useState, useEffect } from "react";
import { useLanguage } from "../contexts/LanguageContext";
import { useDarkMode } from "../contexts/DarkModeContext";
import {
  Package,
  Plus,
  Edit,
  Trash2,
  Search,
  MapPin,
  UserPlus,
  Eye,
  EyeOff,
  Save,
  X,
  Box,
  ArrowLeft,
  FileText,
} from "lucide-react";
import axios from "axios";

const Items = () => {
  const { t } = useLanguage();
  const { isDarkMode } = useDarkMode();
  const [items, setItems] = useState([]);
  const [lockers, setLockers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [lockerFilter, setLockerFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    locker_id: "",
    description: "",
    status: "",
  });
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [itemsResponse, lockersResponse] = await Promise.all([
        axios.get("/api/items"),
        axios.get("/api/lockers"),
      ]);
      setItems(itemsResponse.data);
      setLockers(lockersResponse.data);
    } catch (error) {
      console.error("Error fetching data:", error);
      setItems([]);
      setLockers([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddItem = async (e) => {
    e.preventDefault();
    try {
      await axios.post("/api/admin/items", formData);
      setShowAddModal(false);
      setFormData({ name: "", locker_id: "", description: "", status: "" });
      fetchData();
    } catch (error) {
      console.error("Error adding item:", error);
      alert(t("failed_add_item"));
    }
  };

  const handleEditItem = async (e) => {
    e.preventDefault();
    try {
      await axios.put(`/api/admin/items/${editingItem.id}`, formData);
      setEditingItem(null);
      setFormData({ name: "", locker_id: "", description: "", status: "" });
      fetchData();
    } catch (error) {
      console.error("Error updating item:", error);
      alert(t("failed_update_item"));
    }
  };

  const handleDeleteItem = async (itemId) => {
    if (!confirm(t("confirm_delete_item"))) return;

    try {
      await axios.delete(`/api/admin/items/${itemId}`);
      fetchData();
    } catch (error) {
      console.error("Error deleting item:", error);
      alert(t("failed_delete_item"));
    }
  };

  const openEditModal = (item) => {
    setEditingItem(item);
    setFormData({
      name: item.name,
      locker_id: item.locker_id || "",
      description: item.description || "",
      status: item.status || "", 
    });
  };

  const closeModal = () => {
    setShowAddModal(false);
    setEditingItem(null);
    setFormData({ name: "", locker_id: "", description: "", status: "" });
  };

  const exportItems = async (format) => {
    try {
      const response = await axios.get(`/admin/export/items?format=${format}`, {
        responseType: "blob",
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      const fileExtensions = {
        csv: "csv",
        excel: "xlsx",
        pdf: "pdf",
      };
      const extension = fileExtensions[format] || format;
      link.setAttribute(
        "download",
        `items_${new Date().toISOString().split("T")[0]}.${extension}`
      );
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error("Error exporting items:", error);
      alert("Failed to export items");
    }
  };

  const filteredItems = items.filter((item) => {
    const matchesSearch = item.name
      .toLowerCase()
      .includes(searchTerm.toLowerCase());
    const matchesLocker =
      lockerFilter === "all" || item.locker_id == lockerFilter;
    const matchesStatus =
      statusFilter === "all" || item.status === statusFilter;

    return matchesSearch && matchesLocker && matchesStatus;
  });

  const totalPages =
    pageSize === "all" ? 1 : Math.ceil(filteredItems.length / pageSize);
  const paginatedItems =
    pageSize === "all"
      ? filteredItems
      : filteredItems.slice(
          (currentPage - 1) * pageSize,
          currentPage * pageSize
        );

  const getVisiblePages = () => {
    if (totalPages <= 6) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    let start = Math.max(1, currentPage - 2);
    let end = Math.min(totalPages, start + 5);
    if (end - start < 5) {
      start = Math.max(1, end - 5);
    }
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  };

  const getLockerName = (lockerId) => {
    const locker = lockers.find((l) => l.id === lockerId);
    return locker ? locker.name || locker.number : t("unknown");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1
          className={`text-3xl font-bold mb-2 ${
            isDarkMode ? "text-white" : "text-gray-900"
          }`}
        >
          {t("items_management")}
        </h1>
        <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
          {t("items_management_description")}
        </p>
      </div>

      {/* Controls */}
      <div className="mb-6 flex flex-col sm:flex-row gap-4 justify-between items-start sm:items-center">
        <div className="flex flex-col sm:flex-row gap-4 flex-1">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder={t("search_items")}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={`pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600 text-white"
                  : "bg-white border-gray-300 text-gray-900"
              }`}
            />
          </div>

          {/* Locker Filter */}
          <select
            value={lockerFilter}
            onChange={(e) => setLockerFilter(e.target.value)}
            className={`px-4 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
              isDarkMode
                ? "bg-gray-700 border-gray-600 text-white"
                : "bg-white border-gray-300 text-gray-900"
            }`}
          >
            <option value="all">{t("all_lockers")}</option>
            {lockers.map((locker) => (
              <option key={locker.id} value={locker.id}>
                {locker.name || locker.number}
              </option>
            ))}
          </select>
          
          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={`px-4 py-2 border rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
              isDarkMode
                ? "bg-gray-700 border-gray-600 text-white"
                : "bg-white border-gray-300 text-gray-900"
            }`}
          >
            <option value="all">{t("all_statuses")}</option>
            <option value="good">{t("good")}</option>
            <option value="incomplete">{t("incomplete")}</option>
            <option value="missing">{t("missing")}</option>
          </select>

          {/* Page Size Selector */}
          <div className="flex items-center space-x-2">
            <span>{t("show")}</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(
                  e.target.value === "all" ? "all" : parseInt(e.target.value)
                );
                setCurrentPage(1);
              }}
              className={`px-2 py-1 border rounded focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                isDarkMode
                  ? "bg-gray-700 border-gray-600 text-white"
                  : "bg-white border-gray-300 text-gray-900"
              }`}
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value="all">{t("all")}</option>
            </select>
            <span>{t("per_page")}</span>
          </div>
        </div>

        {/* Add Item Button */}
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          <span>{t("add_item")}</span>
        </button>
      </div>

      {/* Export Buttons */}
      <div className="mb-6 flex justify-end space-x-2">
        <button
          onClick={() => exportItems("csv")}
          className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
        >
          <FileText className="h-4 w-4" />
          <span>Export as CSV</span>
        </button>
        <button
          onClick={() => exportItems("excel")}
          className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <FileText className="h-4 w-4" />
          <span>Export as Excel</span>
        </button>
        <button
          onClick={() => exportItems("pdf")}
          className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
        >
          <FileText className="h-4 w-4" />
          <span>Export as PDF</span>
        </button>
      </div>

      {/* Items Table */}
      <div className={`card ${isDarkMode ? "bg-gray-800" : "bg-white"}`}>
        {paginatedItems.length === 0 ? (
          <div className="text-center py-12">
            <Package className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3
              className={`text-lg font-medium mb-2 ${
                isDarkMode ? "text-white" : "text-gray-900"
              }`}
            >
              {t("no_items_found")}
            </h3>
            <p className={`${isDarkMode ? "text-gray-300" : "text-gray-600"}`}>
              {searchTerm || lockerFilter !== "all"
                ? t("try_adjusting_search")
                : t("get_started_adding_item")}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className={`${isDarkMode ? "bg-gray-700" : "bg-gray-50"}`}>
                <tr>
                  <th
                    className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${
                      isDarkMode ? "text-gray-300" : "text-gray-500"
                    }`}
                  >
                    {t("item")}
                  </th>
                  <th
                    className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${
                      isDarkMode ? "text-gray-300" : "text-gray-500"
                    }`}
                  >
                    {t("status")}
                  </th>
                  <th
                    className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${
                      isDarkMode ? "text-gray-300" : "text-gray-500"
                    }`}
                  >
                    {t("locker")}
                  </th>
                  <th
                    className={`px-6 py-3 text-left text-xs font-medium uppercase tracking-wider ${
                      isDarkMode ? "text-gray-300" : "text-gray-500"
                    }`}
                  >
                    {t("actions")}
                  </th>                                 
                </tr>
              </thead>
              <tbody
                className={`divide-y ${
                  isDarkMode ? "divide-gray-700" : "divide-gray-200"
                }`}
              >
                {paginatedItems.map((item) => (
                  <tr
                    key={item.id}
                    className={`${
                      isDarkMode
                        ? "bg-gray-800 hover:bg-gray-700"
                        : "bg-white hover:bg-gray-50"
                    }`}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="flex-shrink-0 h-10 w-10">
                          <div className="h-10 w-10 rounded-full flex items-center justify-center bg-blue-100">
                            <Package className="h-4 w-4 text-blue-600" />
                          </div>
                        </div>
                        <div className="ml-4">
                          <div
                            className={`text-sm font-medium ${
                              isDarkMode ? "text-white" : "text-gray-900"
                            }`}
                          >
                            {item.name}
                          </div>
                          <div
                            className={`text-sm ${
                              isDarkMode ? "text-gray-300" : "text-gray-500"
                            }`}
                          >
                            ID: {item.id}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                          item.status === "good"
                            ? "bg-green-100 text-green-800"
                            : item.status === "incomplete"
                            ? "bg-yellow-100 text-yellow-800"
                            : item.status === "missing"
                            ? "bg-red-100 text-red-800"
                            : "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {item.status || t("unknown")}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <MapPin className="h-4 w-4 text-gray-400 mr-2" />
                        <span
                          className={`text-sm ${
                            isDarkMode ? "text-gray-300" : "text-gray-900"
                          }`}
                        >
                          {getLockerName(item.locker_id)}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex space-x-2">
                        <button
                          onClick={() => openEditModal(item)}
                          className="text-blue-600 hover:text-blue-900"
                          title={t("edit_item")}
                        >
                          <Edit className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteItem(item.id)}
                          className="text-red-600 hover:text-red-900"
                          title={t("delete_item")}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination Controls */}
      {pageSize !== "all" && totalPages > 1 && (
        <div className="flex justify-center items-center mt-6 space-x-2">
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="px-3 py-1 rounded border bg-gray-200 text-gray-700 disabled:opacity-50"
          >
            &lt;
          </button>
          {getVisiblePages().map((pageNum) => (
            <button
              key={pageNum}
              onClick={() => setCurrentPage(pageNum)}
              className={`px-3 py-1 rounded border ${
                currentPage === pageNum
                  ? "bg-primary-600 text-white"
                  : "bg-gray-200 text-gray-700"
              }`}
            >
              {pageNum}
            </button>
          ))}
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="px-3 py-1 rounded border bg-gray-200 text-gray-700 disabled:opacity-50"
          >
            &gt;
          </button>
          <span className="ml-2 text-sm text-gray-500">
            {t("of")} {totalPages}
          </span>
        </div>
      )}

      {/* Add Item Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className={`max-w-md w-full mx-4 rounded-lg shadow-xl ${
              isDarkMode ? "bg-gray-800" : "bg-white"
            }`}
          >
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <h3
                className={`text-lg font-medium ${
                  isDarkMode ? "text-white" : "text-gray-900"
                }`}
              >
                {t("add_new_item")}
              </h3>
              <button
                onClick={closeModal}
                className={`p-1 rounded-md ${
                  isDarkMode
                    ? "text-gray-400 hover:text-white"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleAddItem} className="p-6 space-y-4">
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("item_name")}
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
              </div>
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("locker")}
                </label>
                <select
                  value={formData.locker_id}
                  onChange={(e) =>
                    setFormData({ ...formData, locker_id: e.target.value })
                  }
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                >
                  <option value="">{t("select_locker")}</option>
                  {lockers.map((locker) => (
                    <option key={locker.id} value={locker.id}>
                      {locker.name || locker.number}
                    </option>
                  ))}
                </select>
              </div>
              {/* État de l’item */}
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("item_status")}
                </label>
                <select
                  value={formData.status || ""}
                  onChange={(e) =>
                    setFormData({ ...formData, status: e.target.value })
                  }
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                >
                  <option value="">{t("select_status")}</option>
                  <option value="good">{t("good")}</option>
                  <option value="incomplete">{t("incomplete")}</option>
                  <option value="missing">{t("missing")}</option>
                </select>
              </div>

              {/* Description de l’item */}
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("description_optional")}
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) =>
                    setFormData({ ...formData, description: e.target.value })
                  }
                  rows={3}
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={closeModal}
                  className={`px-4 py-2 border rounded-md ${
                    isDarkMode
                      ? "border-gray-600 text-gray-300 hover:bg-gray-700"
                      : "border-gray-300 text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {t("cancel")}
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
                >
                  {t("add_item")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Item Modal */}
      {editingItem && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div
            className={`max-w-md w-full mx-4 rounded-lg shadow-xl ${
              isDarkMode ? "bg-gray-800" : "bg-white"
            }`}
          >
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <h3
                className={`text-lg font-medium ${
                  isDarkMode ? "text-white" : "text-gray-900"
                }`}
              >
                {t("edit_item")}
              </h3>
              <button
                onClick={closeModal}
                className={`p-1 rounded-md ${
                  isDarkMode
                    ? "text-gray-400 hover:text-white"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleEditItem} className="p-6 space-y-4">
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("item_name")}
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
              </div>
              {/* État de l’item */}
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("item_status")}
                </label>
                <select
                  value={formData.status || ""}
                  onChange={(e) =>
                    setFormData({ ...formData, status: e.target.value })
                  }
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                >
                  <option value="">{t("select_status")}</option>
                  <option value="good">{t("good")}</option>
                  <option value="incomplete">{t("incomplete")}</option>
                  <option value="missing">{t("missing")}</option>
                </select>
              </div>

              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("locker")}
                </label>
                <select
                  value={formData.locker_id}
                  onChange={(e) =>
                    setFormData({ ...formData, locker_id: e.target.value })
                  }
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                >
                  <option value="">{t("select_locker")}</option>
                  {lockers.map((locker) => (
                    <option key={locker.id} value={locker.id}>
                      {locker.name || locker.number}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  className={`block text-sm font-medium mb-2 ${
                    isDarkMode ? "text-white" : "text-gray-700"
                  }`}
                >
                  {t("description_optional")}
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) =>
                    setFormData({ ...formData, description: e.target.value })
                  }
                  rows={3}
                  className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-primary-500 focus:border-transparent ${
                    isDarkMode
                      ? "bg-gray-700 border-gray-600 text-white"
                      : "bg-white border-gray-300 text-gray-900"
                  }`}
                />
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  type="button"
                  onClick={closeModal}
                  className={`px-4 py-2 border rounded-md ${
                    isDarkMode
                      ? "border-gray-600 text-gray-300 hover:bg-gray-700"
                      : "border-gray-300 text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  {t("cancel")}
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
                >
                  {t("save_changes")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Back Button */}
      <div className="mt-8 text-center">
        <button
          onClick={() => (window.location.href = "/")}
          className={`inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium ${
            isDarkMode
              ? "bg-gray-700 text-white hover:bg-gray-600 border-gray-600"
              : "bg-white text-gray-700 hover:bg-gray-50"
          }`}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t("back_to_main_menu")}
        </button>
      </div>
    </div>
  );
};

export default Items;
